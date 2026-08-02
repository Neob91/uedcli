"""Actor/stash/prefab rendering orchestration.

The shared block from world bounds through preview render output: brush/point extraction, the
`--frame`/`--highlight`/`--focus`/`--show` argument interpretation, per-point-actor render-data
preparation, the mover resolution a filled render needs, and the host-side PNG write. Used by every
preview family (actor, stash, prefab). The thin family preview ENTRY functions stay with their family
(dispatch for now); they call `rendering.render_actors_to_out(...)` / `rendering.brush_actors_from(...)`.

Public seams: `render_actors_to_out`, `brush_actors_from`, `preview_movers` (callers use
module-qualified lookup so an owner-module patch reaches them). Imports only earlier owners
(`resources`, `errors`) and lower services, never a command family (spec "Dependency rules" 4-5).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from .. import config, preview, rotation, surface
from ..classindex import ClassRefError
from ..model import parse_t3d
from ..uprops import SchemaError
from . import resources
from .errors import CommandError, ProjectError


def _poly_world_aabb(actor, indices) -> tuple[float, float, float, float, float, float]:
    """World AABB enclosing the given poly indices of `actor` (honours Rotation/PrePivot/scale)."""
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    R = rotation.actor_linear(actor)
    pp = rotation.actor_prepivot(actor)
    pts = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2]))
           for idx in indices
           for w in (rotation.local_offset(R, pp, v) for v in actor.brush.polys[idx].vertices)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))


def _world_aabb(actors, render_data: "preview.PreviewData") -> tuple | None:
    """World AABB of the whole rendered set (brush vertices + point Locations ± decoration extent),
    or None if nothing has extent — the reference frame `--frame-tightness` interpolates FROM."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for a in actors:
        if a.brush is not None:
            for x, y, z in rotation.world_vertices(a):
                xs.append(x); ys.append(y); zs.append(z)
        else:
            loc = a.location or (Decimal(0), Decimal(0), Decimal(0))
            lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
            e = (preview.point_extent(render_data.points[a.name])
                 if a.name in render_data.points else 0.0)
            xs += [lx - e, lx + e]; ys += [ly - e, ly + e]; zs += [lz - e, lz + e]
    if not xs:
        return None
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _find_actor_in_set(actors, name: str):
    """The actor named `name` (case-insensitive) within the previewed set, or a clean error."""
    hit = next((a for a in actors if a.name.casefold() == name.casefold()), None)
    if hit is None:
        raise CommandError(f"no actor named {name!r} in the previewed set")
    return hit


def _resolve_zoom(actors, selector: str, render_data) -> tuple:
    """A `--frame` SELECTOR → a world AABB. A bare **NAME** frames that actor's whole AABB (a brush's
    vertices, or a point actor's Location ± decoration extent); **`BRUSH:idx`** frames ONE poly (a
    multi-index / `all` selector is a clean error). The name must be in the previewed set. (An explicit
    six-field AABB `--frame` never reaches here — `_parse_frame` splits it off.)"""
    if ":" in selector:
        brush_name, sel = surface.parse_poly_selector(selector)
        actor = _find_actor_in_set(actors, brush_name)
        if actor.brush is None:
            raise CommandError(f"--frame: {actor.name!r} is a point actor (no polys to frame)")
        indices = surface.resolve_polys(sel, actor, brush_name=actor.name)
        if len(indices) != 1:
            raise CommandError(f"--frame BRUSH:idx frames ONE poly; {selector!r} selects "
                                 f"{len(indices)} (use --highlight for a set)")
        return _poly_world_aabb(actor, indices)
    actor = _find_actor_in_set(actors, selector)         # bare NAME → the whole actor's AABB
    box = _world_aabb([actor], render_data)
    if box is None:
        raise CommandError(f"--frame: {actor.name!r} has no extent to frame")
    return box


def _parse_frame(frame: str | None) -> tuple[tuple | None, str | None]:
    """A `--frame` value → `(explicit_region, selector)`, at most one set. **Six numeric comma fields**
    (`X0,Y0,Z0,X1,Y1,Z1`) is an explicit world AABB; anything else is a `BRUSH[:IDX]` selector (a
    real actor name is an identifier, never six comma-joined numbers, so there is no ambiguity)."""
    if not frame:
        return None, None
    parts = frame.split(",")
    if len(parts) == 6:
        try:
            return tuple(float(p) for p in parts), None
        except ValueError:
            pass                                         # e.g. `Wall:1,2,3,4,5,6` → a poly-set selector
    return None, frame


_SHOW_MEMBERS = ("collision", "light-range", "sound-range")


def _parse_show_set(text: str) -> set[str]:
    """The `--show` comma-set → a validated member set (union). Unknown members are a clean named error
    (the CLI 'errors name the offending value' rule), not a silent drop."""
    members = {t.strip() for t in text.split(",") if t.strip()}
    if unknown := members - set(_SHOW_MEMBERS):
        raise CommandError(f"--show: unknown member(s) {', '.join(sorted(unknown))}; "
                             f"valid: {', '.join(_SHOW_MEMBERS)}")
    return members


def _resolve_highlights(actors, args) -> tuple[set, set, list]:
    """`--highlight POLY|NAME` (repeatable) → `(highlight_polys, highlight_points, requests)`. A token
    WITH a colon is a poly selector BRUSH:idx (set form) → `(actor_name, poly_idx)` pairs; a token
    WITHOUT a colon is an ACTOR NAME → resolved case-insensitively in the previewed set: a brush actor
    contributes ALL its poly indices (whole-brush highlight), a point actor its name. A selector
    naming a point actor, or any name/brush not in the set → clean named error, never a traceback.

    `requests` groups the poly keys BY TOKEN — `(actor_name, keys, whole)` per brush token — so a caller
    can report a highlight that landed on nothing at the granularity the USER asked at
    (`_note_invisible_highlights`). `whole` is read off the token FORM, not the resulting count: a bare
    name and `BRUSH:all` mean "this brush", while `BRUSH:1,2` names faces even if the list happens to
    cover all of them. The form is what says which granularity the user was thinking in."""
    polys: set = set()
    points: set = set()
    requests: list = []
    for token in getattr(args, "highlight", None) or []:
        if ":" in token:                                 # BRUSH:idx poly selector
            brush_name, sel = surface.parse_poly_selector(token)
            actor = _find_actor_in_set(actors, brush_name)
            if actor.brush is None:
                raise CommandError(f"--highlight: {actor.name!r} is a point actor (no polys)")
            keys = {(actor.name, idx) for idx in surface.resolve_polys(sel, actor,
                                                                      brush_name=actor.name)}
            whole = sel.strip().casefold() == "all"
        else:                                            # bare actor name
            actor = _find_actor_in_set(actors, token)
            if actor.brush is None:
                points.add(actor.name)
                continue
            keys = {(actor.name, idx) for idx in range(len(actor.brush.polys))}
            whole = True
        polys |= keys
        requests.append((actor.name, keys, whole))
    return polys, points, requests


def _note_invisible_highlights(requests: list, shown: set) -> None:
    """Say on STDERR when a `--highlight` landed on nothing visible, naming the selectors.

    Under a filled mode a highlighted face that other geometry hides draws nothing at all (owner ruling:
    a highlight re-colours what is visible and is never an x-ray). That is a correct render, so it is NOT
    an error — but silence would leave the user unable to tell "that face is not shown" from "I mistyped
    the index" or "the flag did not take". **stderr, never stdout**: a preview writes its image to
    `--out`, and human-facing remarks must never enter a pipe (`direction/conventions.md`).

    **It names no CAUSE, deliberately.** Several different things make a highlight draw nothing and they are
    not distinguishable from `shown`: depth hid the face, the subtract cull dropped a camera-facing poly (no
    view will ever reveal that one), `PF_Invisible` removed it, the framing clipped it off-canvas, or the
    poly has no vertices to project at all. An earlier wording said "hidden behind other geometry at this
    `--view`", which is false for most of those and misleading under `--layout quad`, where the note fires
    only if NO pane saw the face.

    **Granularity follows the TOKEN FORM, not the face.** A whole-brush highlight (`--highlight Wall` or
    `Wall:all`) is reported only if the WHOLE brush came out invisible, because a closed brush ALWAYS has
    hidden back faces — per-face reporting there would fire on every such run, noise that would train the
    reader to ignore the note. A token naming faces (`Wall:3`, `Wall:1,2,3`) reports exactly the ones that
    drew nothing, which is actionable and is the granularity that user was already thinking in.

    **Nearly, but not quite, unreachable under `--faces wire`.** Nothing is ever hidden by depth there, so
    a face that survives projection always draws — but a poly with NO projectable vertices is dropped
    before the edge loop in either mode, so a degenerate `--from-t3d` poly can trip the note under `wire`
    too. Reporting that is correct; the earlier claim that `wire` was structurally exempt was not."""
    missing: list[str] = []
    for name, keys, whole in requests:
        if whole:
            if not keys & shown:                         # the entire brush came out invisible
                missing.append(name)
        else:
            missing += [f"{n}:{i}" for n, i in sorted(keys - shown)]
    seen: set = set()                                    # a repeated token must not be listed twice
    unique = [m for m in missing if not (m in seen or seen.add(m))]
    if unique:
        # "no HIGHLIGHT was drawn", not "nothing was drawn": an index `--annotate` asked for is
        # deliberately kept on a hidden face (numbering is facing-blind and grades hidden faces down), so
        # on the default `--annotate` that face's number IS on the image — measured at 349 px.
        print(f"note: --highlight {', '.join(unique)} is not visible in this render, so no highlight was "
              f"drawn for it", file=sys.stderr)


def _resolve_focus(actors, args) -> str | None:
    """`--focus BRUSH` → the canonical brush name to spotlight, or None. The name must be a BRUSH in the
    previewed set: an unknown name or a point actor is a clean named error (never a traceback), per the
    'no exception reaches the user' rule."""
    focus = getattr(args, "focus", None)
    if focus is None:
        return None
    actor = _find_actor_in_set(actors, focus)            # raises CommandError if absent
    if actor.brush is None:
        raise CommandError(f"--focus: {actor.name!r} is a point actor (focus applies to a brush)")
    return actor.name


_BREAKDOWN_GAP = 8            # px between grid cells
_BREAKDOWN_CAPTION_H = 16     # px band above each cell for its caption
_BREAKDOWN_PAD = 16          # px border around the geometry in every pane (minimal, consistent padding)
_BREAKDOWN_WARN_PANES = 16    # more panes than this → a stderr "large selection" warning
_BREAKDOWN_POINT_MARGIN = 32.0  # a point pane frames Location ± this (world UU) — a real box, never


def _point_pane_region(point, render_data) -> tuple:
    """Framing AABB for a point actor's breakdown pane: its `_world_aabb` (Location ± sprite footprint),
    EXPANDED to at least `Location ± _BREAKDOWN_POINT_MARGIN` per axis. A marker-only point has a
    zero-size `_world_aabb` (its footprint is 0), which `_framing` would collapse to a 1-unit window and
    jam the marker into a corner; the margin guarantees a real, centred window regardless."""
    loc = point.location or (Decimal(0), Decimal(0), Decimal(0))
    lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
    box = _world_aabb([point], render_data) or (lx, ly, lz, lx, ly, lz)
    x0, y0, z0, x1, y1, z1 = box
    return (min(x0, lx - _BREAKDOWN_POINT_MARGIN), min(y0, ly - _BREAKDOWN_POINT_MARGIN),
            min(z0, lz - _BREAKDOWN_POINT_MARGIN), max(x1, lx + _BREAKDOWN_POINT_MARGIN),
            max(y1, ly + _BREAKDOWN_POINT_MARGIN), max(z1, lz + _BREAKDOWN_POINT_MARGIN))


def _render_breakdown_grid(actors, args, *, render_data, shown_highlights=None,
                           grid=None, cells_out=None) -> bytes:
    """`--layout breakdown`: a near-square GRID of panes, returned as a Pillow **Image** (the panes
    themselves are PPM bytes from the stdlib renderer; the stitch is already Pillow, so the caller
    writes this Image straight to PNG instead of re-encoding it through PPM). Pane 0 is the whole scene in CSG
    colour — a plain spatial map, NO legend, names, or numbers. Each following pane is ONE actor,
    captioned with its name: a BRUSH is `--focus`ed + zoomed to its own AABB with all its faces
    numbered; a POINT actor is zoomed to a box around its Location with its marker/sprite drawn (no
    poly numbers — a point has no faces). Panes follow the actor-set order (brushes and point actors
    intermixed as they appear), laid into `ceil(sqrt(n))` square cells and stitched with Pillow. It sets
    its own focus/zoom per pane, so it ignores `--frame`/`--focus`; it honours
    `--view`/`--size`/`--annotate`/`--brush-colors`/`--highlight`/`--show`."""
    size, view = args.size, args.view
    # `--brush-colors` parses with `default=None` so an EXPLICIT value is distinguishable from a
    # defaulted one; `getattr`'s own default does NOT fire for an existing-but-None attribute, so the
    # `or "csg"` is what keeps None out of `preview`, where the `legend` test would silently fall
    # through to the CSG branch. Every consumer needs it — this is one of three.
    brush_colors = getattr(args, "brush_colors", "csg") or "csg"
    faces = _preview_faces_mode(args)
    annotation_spec = preview.parse_annotation_spec(args.annotate)
    highlight_polys, highlight_points, _requests = _resolve_highlights(actors, args)
    try:
        from io import BytesIO
        from PIL import Image, ImageDraw
    except ImportError as e:                             # Pillow absent (broken install)
        raise CommandError(f"--layout breakdown needs Pillow, which failed to import: {e}")

    def _pane(*, annotations, focus, region, grid=None, cells_out=None) -> bytes:
        # No legend or overview names anywhere in the breakdown — the SCENE pane is a plain CSG map and
        # the per-actor panes are captioned. A tight `_BREAKDOWN_PAD`-px frame border keeps padding
        # minimal and CONSISTENT across panes (a fixed screen border, not a per-actor world margin).
        # The addressable grid rides ONLY the SCENE pane (pane 0); per-actor panes render as before.
        return preview.render_brushes_pgm(
            actors, view=view, size=size, annotations=annotations, iso_angle=args.iso_angle, region=region,
            highlight_polys=highlight_polys, highlight_points=highlight_points, color_by_csg=True,
            render_data=render_data, focus=focus, draw_legend=False, reserve_legend=False,
            brush_colors=brush_colors, faces=faces, frame_pad=_BREAKDOWN_PAD,
            shown_highlights=shown_highlights, grid=grid, cells_out=cells_out)

    # Pane 0: the whole scene in CSG — a plain spatial map, NO labels (actors are identified by their
    # own captioned panes below). It alone carries the grid gutter + cell legend (single-view).
    panes = [("SCENE", _pane(annotations=preview.parse_annotation_spec("none"), focus=None, region=None,
                             grid=grid, cells_out=cells_out))]
    for a in actors:                                     # one focused + zoomed pane per actor, in order
        if a.brush is not None:                          # brush: focus + frame its own vertex AABB
            panes.append((a.name.upper(),
                          _pane(annotations=annotation_spec, focus=a.name, region=_world_aabb([a], render_data))))
        else:                                            # point: frame a box around its Location (focus
            panes.append((a.name.upper(),                # is brush-only, so leave it off — the tight
                          _pane(annotations=annotation_spec, focus=None,   # zoom + caption identify the point)
                                region=_point_pane_region(a, render_data))))
    n = len(panes)
    cols = math.ceil(math.sqrt(n))                       # near-square, slightly wider than tall
    rows = math.ceil(n / cols)
    cell_h = size + _BREAKDOWN_CAPTION_H                 # each cell = caption band + square pane
    grid_w = cols * size + (cols - 1) * _BREAKDOWN_GAP
    grid_h = rows * cell_h + (rows - 1) * _BREAKDOWN_GAP
    grid_img = Image.new("RGB", (grid_w, grid_h), (245, 245, 245))
    draw = ImageDraw.Draw(grid_img)
    for i, (caption, ppm) in enumerate(panes):
        r, c = divmod(i, cols)
        x = c * (size + _BREAKDOWN_GAP)
        y = r * (cell_h + _BREAKDOWN_GAP)
        grid_img.paste(Image.open(BytesIO(ppm)).convert("RGB"), (x, y + _BREAKDOWN_CAPTION_H))
        draw.text((x + 4, y + 3), caption, fill=(0, 0, 0))
    n_brushes = sum(1 for a in actors if a.brush is not None)
    n_points = len(actors) - n_brushes
    print(f"breakdown: {n_brushes} brushes, {n_points} point actors, {n} panes, "
          f"{cols}x{rows} grid, {grid_w}x{grid_h} px", file=sys.stderr)
    if n > _BREAKDOWN_WARN_PANES:
        print(f"warning: --layout breakdown produced {n} panes — a large selection; consider a subset",
              file=sys.stderr)
    return grid_img          # a Pillow Image — the write boundary encodes it to PNG directly


_GRID_MAX = 52                       # cap so single-letter/short column addresses stay legible
_QUAD_PANE_ORDER = ("Top", "Front", "Side", "Iso")   # legend/JSON pane order (see spec)


def _view_pane_key(view: str) -> str:
    """A single-view render's one pane key — its `--view`, capitalized to match the quad pane names."""
    return view.capitalize()


def _grid_legend_lines(actors, panes: dict, n: int) -> list[str]:
    """The always-on stderr legend: a density header, then one line per actor in SCENE order. A single
    pane (single/breakdown) is unqualified (`Pillar  D4  (C3–E5)`); multiple panes (quad) are
    pane-qualified (`Pillar  Top:D4 Front:B7 …`). An actor hidden in every pane appends `(hidden)`.
    Same-cell collisions each keep their own line."""
    lines = [f"grid: {n}×{n} columns A–{preview._col_label(n - 1)}, rows 1–{n}"]
    quad = len(panes) > 1
    for a in actors:
        cells = {p: c[a.name] for p, c in panes.items() if a.name in c}
        if not cells:
            continue                                     # degenerate — noted separately, not listed
        if quad:
            body = " ".join(f"{p}:{cells[p].cell}" for p in _QUAD_PANE_ORDER if p in cells)
        else:
            only = next(iter(cells.values()))
            body = only.cell + (f"  ({only.span})" if only.span else "")
        line = f"{a.name}  {body}"
        if all(c.hidden for c in cells.values()):        # invisible in every pane
            line += "  (hidden)"
        lines.append(line)
    return lines


def _grid_json(image_path: str, actors, panes: dict, n: int) -> dict:
    """The `--json` object: `{image, grid:{cols,rows}, actors:{name:{panes:{Pane:{cell,span}}, hidden}}}`.
    Uniform pane-keyed shape across every layout, so a script reads them all the same way."""
    order = _QUAD_PANE_ORDER if len(panes) > 1 else list(panes)
    out_actors: dict = {}
    for a in actors:
        cells = {p: c[a.name] for p, c in panes.items() if a.name in c}
        if not cells:
            continue
        out_actors[a.name] = {
            "panes": {p: {"cell": cells[p].cell, "span": cells[p].span}
                      for p in order if p in cells},
            "hidden": all(c.hidden for c in cells.values()),
        }
    return {"image": image_path, "grid": {"cols": n, "rows": n}, "actors": out_actors}


def render_actors_to_out(actors, args) -> int:
    show = _parse_show_set(getattr(args, "show", ""))    # validate ALWAYS (even a brush-only set)
    render_data = _preview_render_data(actors, args, show)
    factor = getattr(args, "frame_tightness", 0.8)
    if not 0.0 <= factor <= 1.0:                         # errors name the offending value (CLI rule)
        raise CommandError(f"--frame-tightness must be in [0, 1], got {factor}")
    grid = getattr(args, "grid", 12)                     # the always-on addressable grid density
    if not 1 <= grid <= _GRID_MAX:
        raise CommandError(f"--grid must be in [1, {_GRID_MAX}], got {grid}")
    m = 16.0                                             # keep the target off the frame edge
    try:
        annotation_spec = preview.parse_annotation_spec(args.annotate)
        highlight_polys, highlight_points, hi_requests = _resolve_highlights(actors, args)
        focus = _resolve_focus(actors, args)
        explicit_region, frame_selector = _parse_frame(getattr(args, "frame", None))
        zoom_target = (_resolve_zoom(actors, frame_selector, render_data)
                       if frame_selector else None)
    except ValueError as e:                              # surface --annotate / selector parse failure
        raise CommandError(str(e))
    faces = _preview_faces_mode(args)
    layout = getattr(args, "layout", "quad")
    if explicit_region is not None:
        # An explicit --frame AABB frames EXACTLY the given world box (+ the standard margin): it is
        # a box the user chose, so --frame-tightness does NOT modulate it (tightness tunes only the
        # --frame SELECTOR target below). Restores the "fits a world AABB" contract.
        x0, y0, z0, x1, y1, z1 = (float(c) for c in explicit_region)
        region = (x0 - m, y0 - m, z0 - m, x1 + m, y1 + m, z1 + m)
    elif zoom_target is not None:
        # --frame-tightness interpolates the frame between the whole-set extent (0 = no zoom) and the
        # target (1 = tightest, target + margin). No target ⇒ nothing to zoom toward, so it is a no-op.
        whole = _world_aabb(actors, render_data)
        tx0, ty0, tz0, tx1, ty1, tz1 = (float(c) for c in zoom_target)
        tgt = (tx0 - m, ty0 - m, tz0 - m, tx1 + m, ty1 + m, tz1 + m)
        if whole is None or factor >= 1.0:
            region = tgt
        elif factor <= 0.0:
            region = None
        else:
            region = tuple(whole[i] * (1 - factor) + tgt[i] * factor for i in range(6))
    else:
        region = None
    if not actors:
        print("warning: nothing to render (empty actor set)", file=sys.stderr)
    # `or "csg"` at each consumer: see `_render_breakdown_grid` for why `getattr`'s default is not
    # enough once `--brush-colors` parses with `default=None`. These are the other two.
    # ONE set across every pane: a face hidden in the Top pane but visible in the Iso pane is a highlight
    # that landed, so the note must subtract the union of what drew, not decide per pane (which would emit
    # up to four copies of a wrong answer under `--layout quad`).
    shown_highlights: set = set()
    # The addressable grid is ALWAYS ON (owner-ruled). `panes` collects each pane's `{actor: ActorCell}`
    # map — keyed by pane name for quad, by the single `--view` otherwise (breakdown reads off pane 0).
    panes: dict = {}
    try:
        if layout == "breakdown":
            single = {}
            data = _render_breakdown_grid(actors, args, render_data=render_data,
                                          shown_highlights=shown_highlights, grid=grid, cells_out=single)
            panes[_view_pane_key(args.view)] = single
        elif layout == "single":
            single = {}
            data = preview.render_brushes_pgm(actors, view=args.view, size=args.size,
                                              annotations=annotation_spec, iso_angle=args.iso_angle,
                                              region=region, highlight_polys=highlight_polys,
                                              highlight_points=highlight_points,
                                              color_by_csg=True, render_data=render_data, focus=focus,
                                              brush_colors=getattr(args, "brush_colors", "csg") or "csg",
                                              faces=faces, shown_highlights=shown_highlights,
                                              grid=grid, cells_out=single)
            panes[_view_pane_key(args.view)] = single
        else:                                            # quad (default)
            data = preview.render_quad_pgm(actors, size=args.size, annotations=annotation_spec,
                                           iso_angle=args.iso_angle, region=region,
                                           highlight_polys=highlight_polys,
                                           highlight_points=highlight_points,
                                           color_by_csg=True, render_data=render_data, focus=focus,
                                           brush_colors=getattr(args, "brush_colors", "csg") or "csg",
                                           faces=faces, shown_highlights=shown_highlights,
                                           grid=grid, cells_out=panes)
    except preview.PreviewAbort as e:                    # a refusal only reachable mid-render
        raise CommandError(str(e)) from None
    _note_invisible_highlights(hi_requests, shown_highlights)
    # Pure host-side write, no container/UnrealEd. `data` is EITHER raw PPM/P6 bytes from
    # `preview.py` (the stdlib-only renderer) OR an already-decoded Pillow Image from the breakdown
    # stitcher, which is a Pillow function already — an Image is written straight out rather than
    # round-tripped back through PPM. PNG is the ONLY on-disk form: PPM is unviewable by browsers,
    # most image viewers and an LLM, which is the audience these previews exist for, so there is no
    # CLI route to raw PPM (decision 2026-07-24 21:57, "no back-compat cruft").
    # A relative --out joins the CWD (standard CLI semantics — 2026-07-17 layout reorg).
    if args.out is not None:
        requested = os.path.abspath(args.out)
        if os.path.isdir(requested):
            # Without this, splitext would turn `--out shots/` into a `shots.png` SIBLING of the
            # directory the caller meant to write into, and `--out ''`/`--out .` into `<cwd>.png` —
            # silently writing somewhere never asked for. (The old PPM path errored here by
            # accident, via IsADirectoryError; make it deliberate.)
            raise CommandError(f"--out must name a file, not an existing directory: {requested}")
        # The extension the caller wrote is REPLACED by .png (the bytes are PNG, so the name must
        # say so). splitext strips only the final-basename extension -- NOT a dot in a parent dir
        # (e.g. --out /a/.cache/pic has no extension and must stay /a/.cache/pic.png).
        host_out = os.path.splitext(requested)[0] + ".png"
    else:
        fd, host_out = tempfile.mkstemp(prefix="uedcli-preview-", suffix=".png")
        os.close(fd)
    try:
        Path(host_out).parent.mkdir(parents=True, exist_ok=True)
        from io import BytesIO
        from PIL import Image
        img = data if isinstance(data, Image.Image) else Image.open(BytesIO(data))
        img.save(host_out)                                   # .png suffix -> Pillow writes PNG
    except ImportError as e:                                 # Pillow absent (broken install)
        raise CommandError(f"writing the preview PNG needs Pillow, which failed to import: {e}")
    except OSError as e:                                     # unwritable path, decode failure, ...
        raise CommandError(f"could not write preview to {host_out}: {e}")
    # Addressable-grid output: the legend ALWAYS to stderr; a degenerate actor with no cell is noted,
    # not listed. stdout is the machine form (--json) OR the bare path — one form, never both.
    addressed = {name for pane in panes.values() for name in pane}
    if unaddressed := [a.name for a in actors if a.name not in addressed]:
        print(f"note: no grid cell for {', '.join(unaddressed)} (no projectable geometry)",
              file=sys.stderr)
    for line in _grid_legend_lines(actors, panes, grid):
        print(line, file=sys.stderr)
    if getattr(args, "json", False):
        print(json.dumps(_grid_json(host_out, actors, panes, grid), indent=2))
    else:
        print(host_out)                 # the rendered HOST file path
    return 0


def write_png(img, out) -> str:
    """Write a Pillow `Image` to `out` as PNG and return the host path actually written — the shared
    `--out` semantics (matching `render_actors_to_out`'s write): a relative `--out` joins the cwd; the
    caller's extension is REPLACED by `.png` (the bytes are PNG, so the name must say so); an existing
    directory is a clean error, never a silent sibling `.png`; with no `--out` a unique temp file is
    minted. Used by `class preview`."""
    if out is not None:
        requested = os.path.abspath(out)
        if os.path.isdir(requested):
            raise CommandError(f"--out must name a file, not an existing directory: {requested}")
        host_out = os.path.splitext(requested)[0] + ".png"
    else:
        fd, host_out = tempfile.mkstemp(prefix="uedcli-class-preview-", suffix=".png")
        os.close(fd)
    try:
        Path(host_out).parent.mkdir(parents=True, exist_ok=True)
        img.save(host_out)
    except OSError as e:
        raise CommandError(f"could not write preview to {host_out}: {e}")
    return host_out


def brush_actors_from(actors_t3d: dict, order: list[str], names: list[str], *,
                       brushes_only: bool = True):
    """The chosen actors parsed out of a stash/prefab T3D blob. `brushes_only` (the historical
    default, kept for any non-preview caller) drops point actors; preview passes False so point
    actors render too (they'd otherwise be silently dropped BEFORE the renderer)."""
    chosen = names or order
    level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen if n in actors_t3d)
                      + "\nEnd Map\n")
    return [level.actors[n] for n in chosen if n in level.actors
            and (not brushes_only or level.actors[n].brush)]


def _strip_object_ref(text: str | None) -> str | None:
    """`Texture'Package.Group.Name'` (or `Class'…'`) → the bare `Package.Group.Name` a
    `TextureResolver` expects; a plain `Package.Name` passes through; `None`/`"None"`/empty → None."""
    if not text:
        return None
    m = re.search(r"'([^']*)'", text)
    ref = m.group(1) if m else text.strip()
    return ref or None if ref and ref != "None" else None


def _to_float(text, default: float) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


def _to_int(text, default: int) -> int:
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return default


def _resolve_point_render(actor, project, *, resolver, show_collision, show_light,
                          show_sound) -> tuple:
    """Resolve one point actor's render fields (instance prop else class default via the
    `resources.class_defaults` seam) into a `preview.PointRender` + a list of stderr notes. May raise
    `uprops.SchemaError` (the caller degrades to an unscaled marker)."""
    from .. import utexture
    defaults = resources.class_defaults(actor.cls, project)
    instance = {k.casefold(): v for k, v in actor.props}

    def field(name: str):
        low = name.casefold()
        if low in instance:
            return instance[low]
        return defaults.get((low, 0))

    notes: list[str] = []
    draw_type = (field("DrawType") or "DT_Sprite").strip()
    draw_scale = _to_float(field("DrawScale"), 1.0)
    sprite = sprite_world = None
    if draw_type == "DT_Sprite":
        bare = _strip_object_ref(field("Texture"))
        got = resolver.resolve(bare) if (resolver and bare) else None
        if isinstance(got, utexture.DecodedTexture):
            fw, fh = preview.sprite_footprint(draw_scale, got.width, got.height)
            if fw > 0 and fh > 0:
                sprite = (got.width, got.height, got.rgb, got.mask)
                sprite_world = (fw, fh)
            else:                                     # DrawScale 0 / zero-size texture → no billboard
                notes.append(f"point actor {actor.name!r}: sprite {bare} has a zero footprint "
                             f"(DrawScale {draw_scale}) — drawing a marker")
        elif bare is None:
            notes.append(f"point actor {actor.name!r}: DT_Sprite with no Texture — drawing a marker")
        elif got is None:
            # NOTHING WAS SEARCHED. `resources.texture_resolver` returned None — no user config, a
            # broken games config, or an empty composed file list — so no package was ever
            # opened. Saying "not found" here would tell a user with no games config that
            # their texture is missing, which sends them to fix the wrong thing.
            notes.append(f"point actor {actor.name!r}: no texture search path is configured, so "
                         f"sprite {bare} was not looked for — drawing a marker (check "
                         f"`project show`)")
        else:
            # The billboard degrades to a marker rather than failing the whole preview, and the
            # note carries the decoder's named case so "the ref is wrong" and "we cannot decode
            # this layout yet" are distinguishable without re-running anything.
            notes.append(f"point actor {actor.name!r}: sprite {bare} did not decode "
                         f"[{got.case}] — drawing a marker: {got.detail}")
    collision = None
    if show_collision and str(field("bCollideActors")).strip() == "True":
        collision = (_to_float(field("CollisionRadius"), 0.0),
                     _to_float(field("CollisionHeight"), 0.0))
    light_radius = None
    if show_light:
        lr = _to_int(field("LightRadius"), 0)
        # `and lr` deliberately treats LightRadius 0 as "unset" (draw nothing) rather than the pinned
        # world_light_radius(0)==25 UU: a 0 here is almost always an unconfigured light, and a 25-UU
        # bubble on every such actor is noise. A real 25-UU reach is authored as LightRadius>0.
        if (field("LightType") or "LT_None").strip() != "LT_None" \
                and _to_int(field("LightBrightness"), 0) and lr:
            light_radius = preview.world_light_radius(lr)
    sound_radius = None
    if show_sound and _strip_object_ref(field("AmbientSound")) is not None:
        sound_radius = preview.world_sound_radius(_to_int(field("SoundRadius"), 0))
    return preview.PointRender(label=actor.name, sprite=sprite, sprite_world=sprite_world,
                               collision=collision, light_radius=light_radius,
                               sound_radius=sound_radius), notes


def _preview_faces_mode(args) -> str:
    """The `--faces` mode for this render. Read with a default because the committed spike harnesses
    build their own arg namespaces and carry no `faces` attribute."""
    return getattr(args, "faces", "wire")


def _preview_verb(args, mode: str) -> str:
    """`actor preview --faces flat` and friends — the verb+flag a `--faces` refusal names."""
    return f"{getattr(args, 'cmd', 'actor')} {getattr(args, 'sub', 'preview')} --faces {mode}"


def preview_movers(actors, args, mode: str) -> frozenset[str]:
    """Which of these brush actors ARE Movers, per `movers.is_mover` over the game's class hierarchy.

    A filled render needs this and cannot guess it: a mover is never carved into the world whatever
    `CsgOper` it carries, so it must escape the subtract cull, and it fills in mover colour. Both
    index-free rules are wrong — the raw `CsgOper` marker renders a `SomethingMover` door inside-out,
    and `preview.classify_brush`'s name guess additionally misses `CEDoor`/`BreakableGlass`, real movers
    whose class names do not end in `Mover`. This is why `flat` loads the class hierarchy and so, unlike
    `wire`, needs the game content available.

    `is_mover` ANSWERS OR RAISES — it never reports an unresolvable class as "not a mover", because
    nothing downstream re-checks. Every unresolvable actor is collected and refused together, grouped by
    cause so each distinct cause is stated once and every offending actor is named.

    **"Needs" is literal here, exactly as it is for textures (decision 2.6).** A set with NO brush actors
    has a trivially known answer — the empty set — so it needs no class index and must not be refused for
    lacking one. Without this, a point-actor-only selection refuses, and an EMPTY selection stops being
    the clean no-op it is under `wire` and becomes exit 2."""
    from .. import movers
    brushes = [a for a in actors if a.brush is not None]
    if not brushes:
        return frozenset()
    verb = _preview_verb(args, mode)
    try:
        index = resources.mover_index(args, verb)
    except ProjectError as e:
        # `resources.mover_index` resolves the project itself, so OUTSIDE one this surfaces as the house "not in
        # a uedcli project" — naming neither the flag that caused it nor why a preview wants a project.
        # On `--from-t3d`, where being outside a project is ordinary and `wire` works fully, that bare
        # message is all the user gets, so it is re-raised naming both.
        raise CommandError(
            f"{verb}: {e} — a filled render resolves every brush's class against Engine.Mover (a mover "
            f"is never carved into the world, so it escapes the subtract cull), and composing the game's "
            f"package search path needs a project. --faces wire needs neither") from None
    out: set[str] = set()
    by_cause: dict[str, list[str]] = {}
    for a in brushes:
        try:
            if movers.is_mover(a, index):
                out.add(a.name)
        except ClassRefError as e:
            by_cause.setdefault(str(e), []).append(a.name)
    if by_cause:
        detail = "\n  ".join(f"{', '.join(names)} — {cause}" for cause, names in by_cause.items())
        raise CommandError(
            f"{verb}: cannot tell a mover from a real subtraction for "
            f"{sum(len(n) for n in by_cause.values())} actor(s), so the fill would be wrong:\n  "
            f"{detail}\n(--faces wire needs no class hierarchy)")
    return frozenset(out)


def _preview_render_data(actors, args, show: set[str]) -> "preview.PreviewData":
    """Everything the preview needs resolved before a pixel is drawn — dispatch owns schema, texture
    and class-hierarchy resolution so `preview.py` stays resolver-free.

    `points` is the per-point-actor render data. `faces` is None under `--faces wire`, which resolves
    nothing and so still works with no game install; under a FILLED mode it carries the mover set (which
    needs the game's class hierarchy) and, under `textured`, the decoded texture payload. The
    mover/texture resolution runs FIRST, so a scene that cannot resolve them does not first emit
    point-actor notes about it."""
    mode = _preview_faces_mode(args)
    faces = None
    if mode != "wire":
        if mode == "textured":
            # Cheap arg/geometry refusals first (§2.7, §4.2), before touching any resolver.
            _reject_explicit_brush_colors(args)
            _reject_transformed_brushes(actors, args)
        movers = preview_movers(actors, args, mode)
        textures = preview_textures(actors, args) if mode == "textured" else None
        faces = preview.FaceData(movers=movers, textures=textures)
    return preview.PreviewData(points=_preview_point_data(actors, args, show), faces=faces)


def _reject_explicit_brush_colors(args) -> None:
    """`--faces textured --brush-colors X` is a clean exit 2 (decision 2.7). `--brush-colors` parses
    with `default=None`, so a non-None value is an EXPLICIT one; textured colours nothing from it (it
    samples each face's own texture), and giving one flag two jobs is refused rather than ignored."""
    chosen = getattr(args, "brush_colors", None)
    if chosen is not None:
        verb = _preview_verb(args, "textured")
        raise CommandError(f"{verb}: --brush-colors {chosen} conflicts with --faces textured. That flag "
                           f"colours the wireframe and the flat fills; textured draws neither — it "
                           f"samples each face's OWN texture. Drop --brush-colors, or use --faces flat")


def _nonidentity_scale_part(fs) -> str:
    """The first non-identity component of an `FScale` (`Scale.X=..` / `SheerRate=..`), or "" for the
    identity transform — for naming which field made a brush ineligible for `textured`."""
    if fs is None or fs.is_identity():
        return ""
    from decimal import Decimal
    for axis, val in zip("XYZ", fs.scale):
        if Decimal(str(val)) != Decimal(1):
            return f"Scale.{axis}={val}"
    return f"SheerRate={fs.sheer_rate}"


def _reject_transformed_brushes(actors, args) -> None:
    """`--faces textured` refuses ANY scaled or sheared brush (§4.2), listing every offender with its
    field (a batch is all-or-nothing). Its geometry is built with the full linear transform
    (`PostScale·R·MainScale`, sheer folded in) while the UV frame uses rotation ONLY, so a texture would
    sit on untransformed axes over transformed geometry — a wrong answer in the one tool meant to be
    authoritative about UV. `wire`/`flat` render these; supporting them under `textured` is deferred."""
    offenders: list[str] = []
    for a in actors:
        if a.brush is None:
            continue
        for field, fs in (("MainScale", a.main_scale), ("PostScale", a.post_scale)):
            part = _nonidentity_scale_part(fs)
            if part:
                offenders.append(f"{a.name} ({field} {part})")
    if offenders:
        verb = _preview_verb(args, "textured")
        raise CommandError(
            f"{verb}: cannot texture {len(offenders)} scaled or sheared brush(es) — the UV frame uses "
            f"rotation only, so the texture would not follow the transformed geometry: "
            f"{', '.join(offenders)}. Remove the scale/sheer, or use --faces wire/flat")


def _texture_resolver_cause(project, verb: str) -> str:
    """Why no texture resolver is available, as one of `_texture_resolver`'s three `None` causes (§8),
    so a scene that NEEDS a texture and has no resolver refuses naming the actual cause — never a
    generic "no project", since all three are reachable WITH a valid project."""
    lead = (f"{verb}: the scene references a texture but no texture search path is available")
    try:
        user_config = config.load_user_config()
    except config.ConfigError as e:
        return f"{lead}: the games config is broken — {e}. (--faces wire/flat need no textures)"
    if user_config is None:
        return (f"{lead}: no per-user games config (~/.uedcli/config.toml) — create it with a "
                f"[games.<name>] paths dir list. (--faces wire/flat need no textures)")
    try:
        files = config.composed_search_files(project, user_config) if project is not None else []
    except config.ConfigError as e:
        return f"{lead}: the games config is broken — {e}. (--faces wire/flat need no textures)"
    if not files:
        return (f"{lead}: this project resolves no game packages (check the games config `paths` and "
                f"that the project targets a game). (--faces wire/flat need no textures)")
    return f"{lead}."                                    # unreachable: a real resolver would have built


def preview_textures(actors, args) -> "preview.TextureData":
    """Resolve every texture the brush faces reference into the decoded seam a `--faces textured` render
    draws from — dispatch owns this so `preview.py` stays resolver-free.

    "Needs" is literal (decision 2.6): the scene's face refs are collected first, and a scene
    referencing NONE renders with no texture source at all. Otherwise every distinct ref is decoded and
    any the render NEEDS and cannot get is a clean exit 2 naming the cause (§8) — an unreadable/bare/
    undecodable ref lists EVERY offender with its case (a bare one says to qualify it as `Package.Name`),
    and no resolver at all names which of the three `None` causes applies. On success: a `TextureData`
    with every ref's mip pyramid (casefolded key, FName semantics) and every textured face's masked
    answer, `(poly.flags | actor PolyFlags) & PF_Masked` OR the decoder's `bMasked` (§4.3a)."""
    from .. import utexture
    brushes = [a for a in actors if a.brush is not None]
    face_ref: dict[tuple[str, int], str] = {}          # (actor, poly) → casefolded ref (faces WITH one)
    refs: dict[str, str] = {}                           # casefold → original spelling (for messages)
    for a in brushes:
        for idx, poly in enumerate(a.brush.polys):
            ref = preview._poly_texture_ref(poly)
            if ref is None:
                continue
            cf = ref.casefold()
            face_ref[(a.name, idx)] = cf
            refs.setdefault(cf, ref)
    if not refs:                                        # decision 2.6: nothing needed, nothing resolved
        return preview.TextureData(by_ref={}, masked={})
    verb = _preview_verb(args, "textured")
    try:
        project = resources.resolve_project(args)
    except ProjectError:
        project = None
    resolver = resources.texture_resolver(project)
    if resolver is None:
        raise CommandError(_texture_resolver_cause(project, verb))
    by_ref: dict[str, list] = {}
    decoded: dict[str, "utexture.DecodedTexture"] = {}
    fails: list[str] = []
    for cf, ref in refs.items():
        got = resolver.resolve(ref)
        if isinstance(got, utexture.DecodedTexture):
            by_ref[cf] = list(got.mips)
            decoded[cf] = got
        else:                                           # a TextureError — collect, refuse the batch
            hint = " — qualify it as Package.Name" if got.case == "unqualified-ref" else ""
            fails.append(f"{ref} [{got.case}] {got.detail}{hint}")
    if fails:
        raise CommandError(
            f"{verb}: {len(fails)} texture(s) the render needs could not be read, so a textured face "
            f"would silently be a checkerboard — refusing instead:\n  " + "\n  ".join(fails))
    masked: dict[tuple[str, int], bool] = {}
    for a in brushes:
        actor_flags = preview.poly_flags_int(dict(a.props))
        for idx, poly in enumerate(a.brush.polys):
            cf = face_ref.get((a.name, idx))
            if cf is None:
                continue
            flag_masked = bool(((poly.flags or 0) | actor_flags) & preview.PF_MASKED)
            masked[(a.name, idx)] = flag_masked or bool(decoded[cf].b_masked)
    return preview.TextureData(by_ref=by_ref, masked=masked)


def _preview_point_data(actors, args, show: set[str]) -> dict:
    """Resolve per-point-actor render data for the preview. `show` is the validated `--show` member set.
    Brush actors are skipped (their geometry needs no schema — which is why a pure-brush `--faces wire`
    preview works with no game install). A point actor whose schema is unresolvable degrades to an
    unscaled labelled marker + a one-line stderr note, NEVER a traceback."""
    point_actors = [a for a in actors if a.brush is None]
    if not point_actors:
        return {}
    show_collision = "collision" in show
    show_light = "light-range" in show
    show_sound = "sound-range" in show
    try:
        project = resources.resolve_project(args)
    except ProjectError:
        project = None
    resolver = resources.texture_resolver(project)
    data: dict = {}
    notes: list[str] = []
    for a in point_actors:
        try:
            pr, n = _resolve_point_render(a, project, resolver=resolver,
                                          show_collision=show_collision, show_light=show_light,
                                          show_sound=show_sound)
            notes.extend(n)
        except (SchemaError, config.ConfigError) as e:
            pr = preview.PointRender(label=a.name)
            notes.append(f"point actor {a.name!r}: schema unavailable ({a.cls}) — drawing an "
                         f"unscaled marker ({e})")
        data[a.name] = pr
    for line in notes:
        print(line, file=sys.stderr)
    return data
