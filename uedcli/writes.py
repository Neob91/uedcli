"""Write primitives — add and _re_add (the paste/import seam used by materialize).

  D6 — uedcli owns a reserved Name namespace; add_actor never lets the editor
       auto-name and refuses a live name collision (IMPORTADD on a live name
       DUPLICATES).

Geometry is validated before any brush edit materializes, so degenerate geometry
never reaches the editor.
"""
from __future__ import annotations

import copy
import subprocess
import uuid
from decimal import Decimal

from .emit import emit_map
from .geometry import validate_brush
from .model import Actor, Level

CONTAINER_TMP = "/work"

NAME_PREFIX = "Uedcli"   # uedcli owns this namespace (D6) — never let the editor auto-name

# EDIT PASTE shifts the pasted actor +PASTE_DRIFT on EVERY axis (paste-only; copy
# has no offset). Verified 2026-06-17: a brush emitted at origin lands at (32,32,32).
PASTE_DRIFT = 32


def _write_container_file(driver, content: str) -> str:
    """Write `content` to a unique file under the container's /work; return
    the container path. Uses `docker exec … tee` so no host/container path skew."""
    path = f"{CONTAINER_TMP}/uedcli_{uuid.uuid4().hex}.t3d"
    subprocess.run(
        ["docker", "exec", "-i", driver.container, "tee", path],
        input=content, text=True, capture_output=True, check=True,
    )
    return path


def allocate_name(level: Level, cls: str) -> str:
    """Pick a fresh uedcli-owned Name for a new actor of `cls`, checked against
    the current level so a later IMPORTADD can't silently duplicate (D6). The
    editor auto-names new actors (Brush64/65/…); we never rely on that."""
    stem = f"{NAME_PREFIX}{cls}"
    i = 0
    while f"{stem}{i}" in level.actors:
        i += 1
    return f"{stem}{i}"


def _ensure_brush_ref(actor: Actor) -> None:
    """A brush actor MUST carry a `Brush=Model'MyLevel.<model>'` prop (pointing at
    its inline brush model). Without it the editor crashes on REBUILD; with it
    emitted BEFORE the brush block the brush is unselectable — emit.py emits it
    after the block (verified). Inject it if a constructed brush lacks it."""
    if actor.brush is not None and not any(k == "Brush" for k, _ in actor.props):
        model = actor.brush.model_name or "Brush"
        actor.props = actor.props + [("Brush", f"Model'MyLevel.{model}'")]


def _shift_for_paste(actor: Actor) -> Actor:
    """A paste-bound copy: pre-subtract PASTE_DRIFT on every axis so the +32uu
    paste drift lands it back at actor.location, and ensure the Brush= ref."""
    s = copy.deepcopy(actor)
    _ensure_brush_ref(s)
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    s.location = (loc[0] - PASTE_DRIFT, loc[1] - PASTE_DRIFT, loc[2] - PASTE_DRIFT)
    return s


def _re_add(driver, actors: list[Actor]) -> None:
    """Re-introduce actors keeping each kind selectable afterwards.

    Point actors -> MAP IMPORTADD (no drift; INSIDE-selects by pivot).
    BRUSHES -> EDIT PASTE (clipboard + paste): the ONLY add verb that yields an
    ACTOR-SELECT-INSIDE-selectable brush — IMPORTADD'd brushes are never selectable
    (verified by cut-and-reimport). Brushes are pre-shifted -PASTE_DRIFT to cancel
    paste drift. (Point-only input reproduces the prior IMPORTADD call exactly.)
    """
    if not actors:
        return
    driver.set_grid(1, 1, 1)
    points = [a for a in actors if a.brush is None]
    brushes = [a for a in actors if a.brush is not None]
    if points:
        driver.map_importadd(_write_container_file(driver, emit_map(points)))
    if brushes:
        driver.set_clipboard(emit_map([_shift_for_paste(a) for a in brushes]))
        driver.edit_paste()


def add_actor(driver, actor: Actor, level: Level | None = None) -> None:
    """Add a new actor (grid 1 for exact coords). Point actors via MAP IMPORTADD;
    BRUSHES via EDIT PASTE so they stay ACTOR-SELECT-INSIDE-selectable for later
    modify/delete/trim. If `level` is given, refuse a name that already exists —
    a live-name collision DUPLICATES on import and renames on paste; the caller
    must allocate_name first (D6). On success, `level.actors` is updated."""
    if level is not None and actor.name in level.actors:
        raise ValueError(
            f"add_actor: name {actor.name!r} already exists — add would "
            f"duplicate/rename (collision); allocate_name() a fresh one"
        )
    if actor.brush:
        validate_brush(actor.brush)
    _re_add(driver, [actor])
    if level is not None:
        level.actors[actor.name] = actor


def actor_bounds(actor: Actor):
    """Axis-aligned (lo, hi) world bounds, honouring the full actor transform
    `Location + PostScale·R·MainScale·(v − PrePivot)`; for a point actor, a zero-size box at Location.
    (Unscaled, unrotated, PrePivot-free builder brushes stay byte-identical to plain Location+v.)"""
    from .rotation import actor_linear, actor_prepivot, local_offset
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    pts = []
    if actor.brush:
        R = actor_linear(actor)
        pp = actor_prepivot(actor)
        for poly in actor.brush.polys:
            for v in poly.vertices:
                w = local_offset(R, pp, v)
                pts.append((loc[0] + w[0], loc[1] + w[1], loc[2] + w[2]))
    if not pts:
        pts = [loc]
    lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
    hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
    return lo, hi


def union_bounds(actors):
    """Axis-aligned (lo, hi) world bounds of a collection of actors."""
    los, his = zip(*(actor_bounds(a) for a in actors))
    lo = (min(p[0] for p in los), min(p[1] for p in los), min(p[2] for p in los))
    hi = (max(p[0] for p in his), max(p[1] for p in his), max(p[2] for p in his))
    return lo, hi


def aabb_within(inner, outer) -> bool:
    """True when AABB `inner`=(lo, hi) is FULLY CONTAINED in AABB `outer`=(lo, hi), edge-inclusive
    (a face sitting exactly on the outer edge counts as contained). Per-axis
    `outer.lo ≤ inner.lo AND inner.hi ≤ outer.hi`. Both boxes come from `actor_bounds` (Decimal),
    so the compare is exact; a point actor's zero-size box is contained iff its Location is in `outer`."""
    (ilo, ihi), (olo, ohi) = inner, outer
    return all(olo[i] <= ilo[i] and ihi[i] <= ohi[i] for i in range(3))

