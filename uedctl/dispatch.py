"""CLI → module glue. Routes verbs against the git-native T3D trunk.

Edits are pure model-side transforms (design D-F): each mutate verb loads the
current level ($UEDCTL_LEVEL) from its on-disk trunk (`maps/<level>/`) via the `TrunkLevelSource`
seam, transforms the in-memory model, maintains `order` via `order_ops`, and
writes the trunk back — no editor in the edit loop. Git is the history (one
`git commit` = one change; the user's own `git`, not uedctl). The editor is
reached only via a per-command ephemeral spin-up (materialize / preview / the
stash CSG generators); the editor read (`_export_editor_level`) is used only on
that build/snapshot path.
"""
from __future__ import annotations

import fcntl
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from .driver import Driver, DriverError      # DriverError → top-level clean-exit catch (no traceback)
from .editor import ensure_editor, stop_editor, EditorBusyError
from .geometry import validate_brush, GeometryError
from .model import parse_t3d, parse_t3d_actors, Actor, CoordinateError, Level
from .normalize import normalize_level, normalize_actor, canonical_actor_t3d, level_order, \
    is_builder_brush
from . import order_ops
from .order_ops import order_after_add, order_after_delete
from .uprops import SchemaError
from .uuid7 import uuid7
from . import (query, writes, preview, rotation, config, level_select, trunk, t3dtree,
               stash_register, stashlib, packages, propedit, uprops, container_assets, classindex,
               folderlib, labellib, schema_cache, surface, utexture)
from .classindex import ClassRefError


# ── the ONE positive-dimension guard shared by every `brush build` shape ──────────────────────
#
# A negative or zero LENGTH silently produces self-overlapping, inside-out geometry: before this
# guard, `brush build staircase --depth -32` exited 0 and emitted a brush whose steps ran backwards
# through each other, surfacing much later as an incomprehensible BSP failure. Rejecting it at the
# front door is one table and one message shape — never a copy-pasted check per verb.
#
# PLUG-IN POINT for a NEW `brush build <shape>`: add ONE row — `"<shape>": {"--flag": "dest", …}`,
# mapping each of the shape's dimension FLAGS (as the user spells them) to its argparse dest. That
# is the whole integration. `test_every_builder_shape_declares_its_positive_dimensions` enumerates
# the real parser and FAILS unless every FLOAT flag of every shape is either listed here or named
# in that test's explicit non-dimension allow-list (the angles below) — so a new shape cannot
# quietly ship a dimension outside this guard, including one that merely has a default.
#
# Deliberately NOT listed: COUNTS (`--steps`, `--sides`, `--segments`) and ANGLES
# (`--angle-per-step`, `--angle`). Their real constraint is tighter than "> 0" — >= 1 step, >= 3
# sides, a sweep under a half turn — and lives next to the geometry reason for it (in `builders.py`
# for the parametric shapes, in `_revolve_sweep`/the spiral branch for the ones checked in unreal
# rotation units before conversion), where the message can name the actual rule. None of them is a
# float flag any more, so none needs an exemption in the test's allow-list either.
_POSITIVE_BUILD_DIMS: dict[str, dict[str, str]] = {
    "cube":      {"--width": "width", "--breadth": "breadth", "--height": "height"},
    "cylinder":  {"--height": "height", "--radius": "radius"},
    "cone":      {"--height": "height", "--radius": "radius"},
    "sheet":     {"--width": "width", "--height": "height"},
    "staircase": {"--depth": "depth", "--rise": "rise", "--breadth": "breadth"},
    "spiral":    {"--inner-radius": "inner_radius", "--step-width": "step_width", "--rise": "rise"},
    "extrude":   {"--depth": "depth"},
    # `revolve` has no float dimension flag at all: its radii ARE the profile's own `u`
    # coordinates, guarded by the stricter "every point strictly off the axis (u > 0)" rule in
    # `_revolve_sweep`, and `--angle`/`--segments` are an angle and a count (see the note above).
    # The row still has to exist — the plug-in-point test requires one per shape.
    "revolve":   {},
}


def _check_positive_build_dims(shape, args) -> None:
    """Reject a non-positive builder dimension BEFORE any geometry is generated. One message shape
    across every builder verb, naming the offending flag and its value (clean exit 2, never a
    traceback). Flags are checked in the table's order, so the message is deterministic when a
    caller passes several bad values at once."""
    for flag, dest in _POSITIVE_BUILD_DIMS.get(shape, {}).items():
        value = getattr(args, dest, None)
        # `not (finite and > 0)` rather than `<= 0`: NaN compares False against EVERYTHING, so a
        # `<= 0` test waves `--width nan` through to fail later as an unrelated-looking geometry
        # error naming no flag. inf is rejected for the same reason (it builds unbounded vertices).
        if value is not None and not (math.isfinite(value) and value > 0):
            raise _SelectionExit(
                f"brush build {shape}: {flag} must be greater than 0, got {value}")


def _align_offset_degrees(args) -> float:
    """`--align-to-side` → the cross-section offset the builder takes, in degrees.

    Half a segment (`180/sides`) turns a FACE rather than a vertex toward the axes, so an n-gon
    pillar sits flush against an axis-aligned wall instead of meeting it on a corner. It is a bool
    at the CLI because that is the only documented use, because any other angle is whole-actor
    placement (`--rotate`), and because a half segment is not exactly representable in unreal
    rotation units for most side counts (a 3-gon's 60° is 10922.67 uu)."""
    return 180.0 / args.sides if getattr(args, "align_to_side", False) else 0.0


def _profile_points(shape: str, args):
    """Parse and validate a swept generator's `--point U,V` profile, in ONE fixed order, before any
    geometry exists: token parse → arity → cleanup (weld + drop collinear) → simple-ring test →
    winding normalization. Returns the cleaned, counter-clockwise ring.

    Every failure is a clean exit 2 naming the offending value. `profile.ProfileError` already
    subclasses `GeometryError` (which `dispatch()` catches without a traceback); it is re-raised as
    `_SelectionExit` here so the message carries the usual `brush build <shape>:` prefix rather than
    the generic "invalid brush geometry" one."""
    from . import profile as profile2d
    tokens = getattr(args, "point", None) or []
    try:
        points = [profile2d.parse_point(t) for t in tokens]
        if len(points) < 3:
            raise profile2d.ProfileError(
                f"a profile needs at least 3 points, got {len(points)}")
        ring = profile2d.clean_profile(points)      # welds + drops collinear; re-checks the arity
        profile2d.check_simple(ring)
        return profile2d.normalize_winding(ring)
    except profile2d.ProfileError as e:
        raise _SelectionExit(f"brush build {shape}: {e}") from None


def _revolve_sweep(args, points) -> tuple[float, int]:
    """Validate `brush build revolve`'s sweep and return `(degrees, segments)`.

    Checked in this fixed order, each failure a clean exit 2 naming the flag AND the value the user
    typed: `--angle` range → the `--segments` default → `--segments` range → the closed-turn
    minimum → the per-facet angle → the strictly-off-axis profile rule.

    Three things here are load-bearing:

    - **The closed-turn minimum is tested BEFORE the per-facet angle**, not after — see the comment
      at that check. A full turn in 1 or 2 segments trips both rules, and `65536/2` is exactly the
      32768 the facet rule rejects, so ordering them the other way would make the closed-turn rule
      unreachable and report the generic facet message for a mistake that has a specific one.

    - **The range check is on the RAW integer, before any conversion**, and the conversion is a
      plain `uu * 360/65536`. `rotation.uu_field`/`uu_to_deg` must NEVER be used: they wrap mod
      65536 because they parse an FRotator *field*, which is inherently modular — but a sweep
      MAGNITUDE is not, and `uu_to_deg(65536)` is `0.0`, so routing a closed full turn through them
      would silently collapse it to a zero sweep.
    - **The `--segments` default is spelled `floor(x + 0.5)`, not `round()`**, which is banker's
      rounding and would make the tie cases surprising.
    """
    angle = args.angle
    if not (0 < angle <= 65536):
        raise _SelectionExit(
            f"brush build revolve: --angle must satisfy 0 < angle <= 65536 unreal rotation units "
            f"(65536 = a full turn), got {angle}")
    segments = args.segments
    if segments is None:
        segments = max(1, math.floor(angle / 4096 + 0.5))   # one facet per 22.5°, UED's own density
    if segments < 1:
        raise _SelectionExit(
            f"brush build revolve: --segments must be at least 1, got {segments}")
    # The closed-turn minimum is tested BEFORE the per-facet rule even though a full turn in 1 or 2
    # segments trips both: its message is the specific one for that mistake, and testing it second
    # would make this rule unreachable (65536/2 is exactly the 32768 the facet rule rejects).
    if angle == 65536 and segments < 3:
        raise _SelectionExit(
            f"brush build revolve: a closed full turn (--angle 65536) needs at least 3 "
            f"--segments, got {segments} — with fewer, the far ring welds onto the near ring and "
            f"every side quad collapses")
    if angle / segments >= 32768:
        raise _SelectionExit(
            f"brush build revolve: --angle {angle} over --segments {segments} is "
            f"{angle / segments:g} uu per facet; a facet of 32768 uu (180°) or more is flat — it "
            f"maps every profile point to its mirror image, giving a zero-volume solid")
    for i, (u, v) in enumerate(points):
        if u <= 0:
            raise _SelectionExit(
                f"brush build revolve: every profile point must sit strictly on the POSITIVE-u "
                f"side of the revolve axis (the line u=0), got point {i} at ({u},{v}) — mirror "
                f"the profile's u values to bulge the other way")
    return angle * 360.0 / 65536.0, segments


def _build_brushes(builders, shape, args):
    """Dispatch `brush build <shape>` to its generator. Returns a Brush or a list of
    Brush (single-element list for convex primitives; staircase → one non-convex
    Brush; extrude and revolve → one swept brush each, non-convex whenever the profile is;
    spiral → a central column plus one wedge tread per step, a list of len > 1). The dispatch
    caller emits one actor per Brush, so the `len(list) > 1` branch stays live for the spiral."""
    _check_positive_build_dims(shape, args)
    if shape == "cube":
        return [builders.cube(args.width, args.breadth, args.height, args.texture)]
    # `--align-to-side` is a BOOL at the CLI and half a segment in DEGREES at the builder: the
    # builders stay a degrees-valued internal API (four direct callers produce editor-blessed
    # parity goldens from angles that are not half-segments at all — decisions.md 2026-07-25 02:30
    # UTC, D11), while the user-facing surface is UU or a bool, never degrees.
    if shape == "cylinder":
        return [builders.cylinder(args.height, args.radius, args.sides, args.texture,
                                  angle_offset=_align_offset_degrees(args))]
    if shape == "cone":
        return [builders.cone(args.height, args.radius, args.sides, args.texture,
                              angle_offset=_align_offset_degrees(args))]
    if shape == "sheet":
        return [builders.sheet(args.width, args.height, args.plane, args.texture,
                               extra_flags=getattr(args, "flags", None))]
    if shape == "staircase":
        return builders.staircase(args.steps, args.depth, args.rise, args.breadth, args.texture)
    if shape == "spiral":
        # The USER-FACING range check, in the units the user typed and naming the flag they typed,
        # BEFORE any conversion (decisions.md 2026-07-25 02:30 UTC, D12). `builders` keeps its own
        # guard for its non-CLI callers, in degrees and naming the parameter.
        per_step = args.angle_per_step
        if not (0 < per_step < 32768):
            raise _SelectionExit(
                f"brush build spiral: --angle-per-step must satisfy 0 < angle < 32768 unreal "
                f"rotation units (32768 = a half turn), got {per_step}")
        return builders.spiral_staircase(args.steps, args.inner_radius, args.step_width,
                                         args.rise, per_step * 360.0 / 65536.0, args.texture)
    if shape == "extrude":
        return [builders.extrude(_profile_points(shape, args), args.depth, args.axis,
                                 args.texture)]
    if shape == "revolve":
        points = _profile_points(shape, args)
        degrees, segments = _revolve_sweep(args, points)
        return [builders.revolve(points, degrees, segments, args.axis, args.texture)]
    raise ValueError(f"unknown builder shape {shape!r}")


def _export_editor_level(driver: Driver) -> Level:
    """MAP EXPORT + parse — the RARE editor read, used only by the build/snapshot path
    (materialize/preview); the trunk is otherwise authoritative."""
    from . import xfer
    path = xfer.work_path("t3d")
    driver.set_grid(1, 1, 1)
    driver.map_export(path)
    txt = subprocess.run(
        ["docker", "exec", driver.container, "cat", path],
        text=True, capture_output=True, check=True,
    ).stdout
    xfer.remove(driver.container, path)
    level = parse_t3d(txt)
    level.order = level_order(level)     # capture export/CSG order BEFORE normalize re-sorts
    normalize_level(level)
    return level


def _capture_from_t3d(text: str, names: list[str], *, index, validate=None,
                      folders: dict[str, str | None] | None = None
                      ) -> tuple[dict, list[str], list, set[str], dict[str, str | None]]:
    """Parse T3D, drop the builder brush, optionally subset by name (a FILTER over source order,
    never a reorder), normalize to bbox-min. Returns (full{name:canonical_t3d}, order, anchor,
    texture_packages, folders{name:folder|None}). `validate(actors)` (if given) runs on the chosen
    set BEFORE serialization — the author-time ingest gate for an EXTERNAL T3D source (it may qualify
    bare classes in place, so it must run before `canonical_actor_t3d` freezes the stored form).

    `folders` is the SOURCE per-name folder map (trunk capture supplies each actor's stored folder;
    an external T3D source has none → all None). Because a T3D blob carries no folder (folder is a
    uedctl-side sidecar), it must be threaded separately (decisions.md 2026-07-18 addendum, sub-choice
    2 — persist folder per member). Trunk actor names are unique so the map keys survive uniquify; an
    external source's None-folders are unaffected by the (dup-only) rename below.

    `index` is the `classindex.ClassIndex` the mover canonicalization gate resolves against
    (`movers.is_mover` is schema-aware since 2026-07-25), so capture needs the game's `.u`
    packages like every other mover-aware verb."""
    from . import stashlib
    from .movers import canonicalize_mover
    # parse_t3d_actors (NOT parse_t3d): user-concatenated T3D may share a Name; the Name-keyed dict
    # would drop all-but-last. Keep an ordered list, drop builder brushes, strip computed props.
    candidates = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    for a in candidates:
        normalize_actor(a)
        # Canonicalize an ingested Mover to KeyNum=0 (spec §3): the unified T3D-tree read path no
        # longer canonicalizes movers on read (the retired `tree_io` did), so a captured EXTERNAL
        # mover at KeyNum!=0 must be folded to base pose HERE or it would round-trip non-canonical.
        canonicalize_mover(a, index)
    # Filter by the `names` subset FIRST, against the RAW source Names, THEN uniquify only the chosen
    # set. (Uniquifying first would suffix a duplicate the user explicitly asked for, so a bare-Name
    # filter would then match only the first — silently re-dropping the rest.)
    requested = set(names)
    missing = requested - {a.name for a in candidates}
    if missing:
        raise _SelectionExit(f"actors not found in source: {', '.join(sorted(missing))}")
    chosen = [a for a in candidates if not requested or a.name in requested]
    if not chosen:
        raise _SelectionExit("capture source has no actors")
    # Uniquify duplicate Names in source order: first occurrence keeps its bare Name, each later
    # collision gets a `<stem>_<rand>` suffix — so none is silently dropped when keyed below.
    seen: set[str] = set()
    for a in chosen:
        if a.name in seen:
            a.name = trunk.alloc_name(a.name.rstrip("0123456789") or a.name, seen)
        seen.add(a.name)
    shifted, anchor = stashlib.normalize_for_capture(chosen)
    if validate is not None:
        validate(shifted)                                # qualify/validate before freezing the T3D
    full = {a.name: canonical_actor_t3d(a) for a in shifted}
    src_folders = folders or {}
    out_folders = {a.name: src_folders.get(a.name) for a in shifted}
    return (full, [a.name for a in shifted], list(anchor),
            stashlib.referenced_packages(shifted), out_folders)


def _auto_slug(reg, order: list[str]) -> str:
    """Collision-resistant: first actor name lowercased, with a -N suffix if taken."""
    base = order[0].lower() if order else "stash"
    existing = set(reg.list_stashes())
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def _resolve_target_names(tokens: list[str]) -> list[str]:
    """The name-source seam for name-taking verbs (`actor delete/rotate/prop/show`): return the RAW
    list of actor names to operate on (canonical resolution + dedup are the CALLER's — spec
    2026-07-18 §8).

    The single token ``-`` reads a newline-separated name list from stdin (exactly `actor find`'s
    output): blank lines dropped, each entry stripped. Empty stdin → ``[]`` (the caller treats that
    as a no-op, exit 0 — a filter that matched nothing is not an error). ``-`` is the SOLE names
    source: mixing it with actual names on the command line raises `_SelectionExit` (exit 2).
    """
    if "-" in tokens:
        if tokens != ["-"]:
            raise _SelectionExit(
                "`-` reads actor names from stdin and cannot be combined with actor "
                "names on the command line")
        data = sys.stdin.read()
        if data.startswith("﻿"):                    # drop a leading UTF-8 BOM (str.strip
            data = data[1:]                              # doesn't — it isn't whitespace) so the
        return [ln.strip() for ln in data.splitlines() if ln.strip()]   # first name resolves
    return list(tokens)


def _reject_nonlevel_target_for_folders(args) -> None:
    """Folder surfaces are TRUNK-ONLY (spec §4): a folder lives only in the per-actor trunk sidecar;
    the flat stash/prefab boxes serialize via `canonical_actor_t3d` (T3D only) and have no per-actor
    sidecar slot. So every folder surface (`actor folder set/unset/get`, `actor add --folder`,
    `actor find --folder/--no-folder`) rejects `--tree stash|prefab` with a clear exit 2, rather
    than silently writing a sidecar that's dropped on save or querying a dimension that's always
    None. `--tree level/NAME` (a named level's trunk) is fine — the guard fires ONLY on
    stash/prefab. Called BEFORE the source is resolved so the message is the right one."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise _SelectionExit("folders apply only to a level (not --tree stash|prefab)")


def _reject_nonlevel_target_for_labels(args) -> None:
    """Label surfaces are TRUNK-ONLY this slice (plan scope-cut): labels live in the per-actor trunk
    `labels` sidecar; the stash/prefab box channel is deferred to the copy-between-trees spec. So
    every label surface (`actor label add/remove/clear/get`, `actor add --label`, `actor find
    --label/--no-label`) rejects `--tree stash|prefab` with a clear exit 2 rather than silently
    dropping a label on a box save. `--tree level/NAME` (a named level's trunk) is fine — the guard
    fires ONLY on stash/prefab. Called BEFORE the source is resolved so the message is the right one.
    Mirrors `_reject_nonlevel_target_for_folders`."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise _SelectionExit("labels apply only to a level (not --tree stash|prefab)")


def _parse_add_order(spec: str) -> tuple[str, str | None]:
    """Parse `actor add --order POS` → (selector, ref). POS is `first` | `last` | `before=NAME` |
    `after=NAME`. A malformed value or an empty NAME raises `_SelectionExit` (clean exit 2)."""
    s = spec.strip()
    low = s.casefold()                                    # selector keyword is case-insensitive
    if low in ("first", "last"):
        return low, None
    for kw in ("before", "after"):
        prefix = kw + "="
        if low.startswith(prefix):
            ref = s[len(prefix):].strip()                 # NAME keeps its case (resolve is case-insensitive)
            if not ref:
                raise _SelectionExit(f"actor add --order {kw}=NAME needs a NAME")
            return kw, ref
    raise _SelectionExit(
        f"actor add --order: expected first|last|before=NAME|after=NAME, got {spec!r}")


def _reject_nonlevel_target_for_order(args) -> None:
    """CSG ordering is TRUNK-ONLY (spec §7): the `order_value` sidecar the ordering verbs rewrite
    lives only in the per-actor trunk layout — stash/prefab boxes use a flat `order` list. So
    `actor order` and `actor add --order <non-last>` reject `--tree stash|prefab` with a clean
    exit 2 rather than silently no-op'ing. Called BEFORE the source is resolved so the message is
    the right one; `--tree level/NAME` (a named level's trunk) is fine."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise _SelectionExit("ordering applies only to a level (not --tree stash|prefab)")


def _actor_folder(args, src) -> int:
    """`actor folder set|unset|get`. The path is on `--to` (set only); names are variadic (or `-`
    from stdin). Validate-all before any write (names resolve all-or-nothing, path grammar) so all
    sidecars land or none do (spec §4). `set`/`unset` are PRODUCERS — each touched Name to stdout, a
    human count to stderr — so they chain like the sibling `actor label` verbs (`find … | folder set
    - --to castle.tower | prop set - …`); the two organizational dimensions behave identically.
    `get` prints the folder per actor in argument order, `(none)` for an unfoldered one."""
    raw = _resolve_target_names(args.names)              # `-` → names from stdin (spec §4)
    if not raw:
        return 0                                          # empty stdin: no-op, exit 0
    if args.foldersub == "set":
        try:
            folderlib.validate_folder_path(args.to)       # grammar-check before touching the trunk
        except ValueError as e:
            raise _SelectionExit(str(e))
    level = src.load()
    try:
        names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if args.foldersub == "get":
        if getattr(args, "json", False):
            import json
            # {name: folder|null} — an unfoldered actor maps to null, not the `(none)` sentinel a
            # script would otherwise have to special-case.
            print(json.dumps({n: level.actors[n].folder for n in names}, indent=2))
            return 0
        for n in names:
            f = level.actors[n].folder
            print(f if f is not None else "(none)")
        return 0
    new = args.to if args.foldersub == "set" else None
    for n in names:
        level.actors[n].folder = new
    src.save(verb="folder", args={"names": names, "folder": new}, level=level, touched=names)
    for name in names:                                    # PRODUCER: touched names → stdout (feed `| verb -`)
        print(name)
    summary = f"set folder {new} on" if args.foldersub == "set" else "unfoldered"
    print(f"{summary} {len(names)} actor(s)", file=sys.stderr)
    return 0


def _actor_label(args, src) -> int:
    """`actor label add|remove|clear|get`. Labels (the values) are on a repeatable `--label`
    (add/remove only); names are variadic (or `-` from stdin). Validate-all-then-apply: every
    `--label` is grammar-checked and every name resolves all-or-nothing BEFORE any write, so a bad
    value leaves the whole tree untouched (spec §4). `add` unions, `remove` subtracts (missing = a
    no-op), `clear` empties. The mutating verbs are PRODUCERS — each touched Name to stdout, a human
    count to stderr — so they chain (`find … | label add - --label lit | prop set - …`). `get` prints
    `Name<TAB>l1,l2` (sorted, comma-joined; unlabelled → `Name<TAB>(none)`), `--json` → `{name: […]}`."""
    raw = _resolve_target_names(args.names)              # `-` → names from stdin (spec §4)
    if not raw:
        return 0                                          # empty stdin: no-op, exit 0
    new_labels: frozenset[str] = frozenset()
    if args.labelsub in ("add", "remove"):
        for lbl in args.label:                            # grammar-check every value before any write
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise _SelectionExit(str(e))
        new_labels = frozenset(args.label)
    level = src.load()
    try:
        names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if args.labelsub == "get":
        if getattr(args, "json", False):
            import json
            print(json.dumps({n: sorted(level.actors[n].labels) for n in names}, indent=2))
            return 0
        for n in names:
            labs = level.actors[n].labels
            print(f"{n}\t{','.join(sorted(labs)) if labs else '(none)'}")
        return 0
    for n in names:
        cur = level.actors[n].labels
        if args.labelsub == "add":
            level.actors[n].labels = cur | new_labels
        elif args.labelsub == "remove":
            level.actors[n].labels = cur - new_labels
        else:                                             # clear
            level.actors[n].labels = frozenset()
    src.save(verb="label", args={"names": names, "sub": args.labelsub}, level=level, touched=names)
    for name in names:                                    # PRODUCER: touched names → stdout (feed `| verb -`)
        print(name)
    summary = {"add": "labelled", "remove": "removed labels from",
               "clear": "cleared labels on"}[args.labelsub]
    print(f"{summary} {len(names)} actor(s)", file=sys.stderr)
    return 0


def _read_t3d_input(path_or_dash: str) -> str:
    """Read T3D text from a file path (or `-` for stdin). An unreadable/missing path is a clean
    error (exit 2) naming the path, never a `FileNotFoundError` traceback."""
    if path_or_dash == "-":
        return sys.stdin.read()
    try:
        with open(path_or_dash) as fh:
            return fh.read()
    except OSError as e:
        raise _SelectionExit(f"cannot read T3D file {path_or_dash!r}: {e.strerror or e}")


def _read_t3d_files(paths: list[str]) -> str:
    """The unified `--from-t3d <FILE…|->` reader: concatenate T3D text from one-or-more files (or
    `-` for a stdin snippet), in order. `-` is the SOLE value if present — no mixing stdin with
    files (the `-` convention). Shared by `actor preview` (T3D mode) and `stash capture`."""
    if "-" in paths and paths != ["-"]:
        raise _SelectionExit("`-` reads a T3D snippet from stdin and cannot be combined with files")
    return "\n".join(_read_t3d_input(p) for p in paths)


def _dispatch_stash(args, reg) -> int:
    if args.sub == "capture":
        # `--tree` names the SOURCE box (explicit alternative to the ambient $UEDCTL_LEVEL); it is
        # only consulted in the trunk branch below, so combining it with an explicit --from-* source
        # would silently ignore one — reject that up front instead of guessing.
        if getattr(args, "tree", None) and args.from_t3d:
            raise _SelectionExit("--tree names the capture SOURCE box; it cannot be combined with "
                                 "--from-t3d")
        # Validate only an EXTERNAL T3D source; capturing from the trunk is already qualified/valid.
        validate = None
        src_folders: dict[str, str | None] = {}          # per-member folders (trunk parity); external → none
        if args.from_t3d:
            text = _read_t3d_files(args.from_t3d)         # <FILE…|-> (multiple concatenate; `-` = stdin)
            validate = lambda actors: _validate_ingest_actors(actors, args)
        else:
            # trunk default = the ambient $UEDCTL_LEVEL (no package manifest; the load set derives at
            # build). Announce which level we captured FROM when it came from the env (visibility guard
            # against a stale export — decisions 2026-07-20); silent with an explicit --tree.
            from .emit import emit_map
            cap_src = _resolve_level_source(args)
            if getattr(cap_src, "from_env", False):
                _announce_env_level(cap_src.display_name, action="capturing from")
            level = cap_src.load()
            # Capture each source actor's stored folder so the stash persists it (a T3D blob can't
            # carry it, so it rides the separate folder channel, decisions 2026-07-18 sub-choice 2).
            src_folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
            text = emit_map([level.actors[n] for n in level.order if n in level.actors])
        full, order, anchor, tex_pkgs, folders = _capture_from_t3d(
            text, args.names, index=_mover_index(args, "stash capture"),
            validate=validate, folders=src_folders)
        packages = sorted(tex_pkgs)
        sid = args.id or _auto_slug(reg, order)
        try:
            reg.write_stash(sid, full_level=full, order=order, packages=packages, folders=folders,
                            force=getattr(args, "force", False),
                            meta={"anchor": [str(c) for c in anchor], "ts": int(time.time() * 1000)})
        except (FileExistsError, ValueError) as e:
            raise _SelectionExit(str(e))
        print(sid)
        return 0
    return _dispatch_stash_reads(args, reg)


def _dispatch_stash_reads(args, reg) -> int:
    from . import stashlib
    if args.sub == "list":
        for sid in reg.list_stashes():
            print(sid)
        return 0
    # Every remaining verb takes an id. An unknown id reads back as empties (register design), which
    # would silently no-op (show/preview) or promote nothing — so validate up front. `reg.exists`
    # keys on `meta.json` (resolves NESTED ids, and stays true for an emptied stash — `--target`
    # editing can delete a stash to zero actors, which content-emptiness can't distinguish from
    # missing). `drop` stays idempotent (a no-op on a missing id, like `rm -f`).
    if args.sub != "drop" and not reg.exists(args.id):
        raise _SelectionExit(f"stash not found: {args.id!r}")
    if args.sub != "drop":
        try:                                             # corrupt meta.json/state → clean, not a traceback
            reg.read_stash(args.id)
        except (OSError, ValueError) as e:
            raise _SelectionExit(f"cannot read stash {args.id!r}: {e}")
    if args.sub == "drop":
        reg.drop_stash(args.id)
        return 0
    if args.sub == "show":
        actors_t3d, order, _pkgs, _meta, _folders = reg.read_stash(args.id)
        chosen = args.names or order
        if args.summary:
            level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen
                                                         if n in actors_t3d) + "\nEnd Map\n")
            print(stashlib.format_summary(args.id, [level.actors[n] for n in chosen
                                                    if n in level.actors]))
        else:
            print("\n".join(actors_t3d[n] for n in chosen if n in actors_t3d))
        return 0
    if args.sub == "preview":
        return _preview_stash(args, reg)              # Task 11
    if args.sub == "apply":
        actors_t3d, order, pkgs, meta, folders = reg.read_stash(args.id)
        return _apply_set(args, _resolve_level_source(args), actors_t3d, order, pkgs,
                          default_group=args.id, anchor=meta.get("anchor", ["0", "0", "0"]),
                          folders=folders)
    if args.sub == "promote":
        return _promote_stash(args, reg)              # Task 15
    raise _SelectionExit(f"unimplemented stash sub-verb: {args.sub}")


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


def _world_aabb(actors, render_data) -> tuple | None:
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
            e = preview.point_extent(render_data[a.name]) if a.name in render_data else 0.0
            xs += [lx - e, lx + e]; ys += [ly - e, ly + e]; zs += [lz - e, lz + e]
    if not xs:
        return None
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _find_actor_in_set(actors, name: str):
    """The actor named `name` (case-insensitive) within the previewed set, or a clean error."""
    hit = next((a for a in actors if a.name.casefold() == name.casefold()), None)
    if hit is None:
        raise _SelectionExit(f"no actor named {name!r} in the previewed set")
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
            raise _SelectionExit(f"--frame: {actor.name!r} is a point actor (no polys to frame)")
        indices = surface.resolve_polys(sel, actor, brush_name=actor.name)
        if len(indices) != 1:
            raise _SelectionExit(f"--frame BRUSH:idx frames ONE poly; {selector!r} selects "
                                 f"{len(indices)} (use --highlight for a set)")
        return _poly_world_aabb(actor, indices)
    actor = _find_actor_in_set(actors, selector)         # bare NAME → the whole actor's AABB
    box = _world_aabb([actor], render_data)
    if box is None:
        raise _SelectionExit(f"--frame: {actor.name!r} has no extent to frame")
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
        raise _SelectionExit(f"--show: unknown member(s) {', '.join(sorted(unknown))}; "
                             f"valid: {', '.join(_SHOW_MEMBERS)}")
    return members


def _resolve_highlights(actors, args) -> tuple[set, set]:
    """`--highlight POLY|NAME` (repeatable) → `(highlight_polys, highlight_points)`. A token WITH a
    colon is a poly selector BRUSH:idx (set form) → `(actor_name, poly_idx)` pairs; a token WITHOUT a
    colon is an ACTOR NAME → resolved case-insensitively in the previewed set: a brush actor
    contributes ALL its poly indices (whole-brush highlight), a point actor its name. A selector
    naming a point actor, or any name/brush not in the set → clean named error, never a traceback."""
    polys: set = set()
    points: set = set()
    for token in getattr(args, "highlight", None) or []:
        if ":" in token:                                 # BRUSH:idx poly selector
            brush_name, sel = surface.parse_poly_selector(token)
            actor = _find_actor_in_set(actors, brush_name)
            if actor.brush is None:
                raise _SelectionExit(f"--highlight: {actor.name!r} is a point actor (no polys)")
            for idx in surface.resolve_polys(sel, actor, brush_name=actor.name):
                polys.add((actor.name, idx))
        else:                                            # bare actor name
            actor = _find_actor_in_set(actors, token)
            if actor.brush is not None:                  # whole-brush highlight = all its polys
                polys.update((actor.name, idx) for idx in range(len(actor.brush.polys)))
            else:
                points.add(actor.name)
    return polys, points


def _resolve_focus(actors, args) -> str | None:
    """`--focus BRUSH` → the canonical brush name to spotlight, or None. The name must be a BRUSH in the
    previewed set: an unknown name or a point actor is a clean named error (never a traceback), per the
    'no exception reaches the user' rule."""
    focus = getattr(args, "focus", None)
    if focus is None:
        return None
    actor = _find_actor_in_set(actors, focus)            # raises _SelectionExit if absent
    if actor.brush is None:
        raise _SelectionExit(f"--focus: {actor.name!r} is a point actor (focus applies to a brush)")
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


def _render_breakdown_grid(actors, args, *, render_data) -> bytes:
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
    brush_colors = getattr(args, "brush_colors", "csg")
    annotation_spec = preview.parse_annotation_spec(args.annotate)
    highlight_polys, highlight_points = _resolve_highlights(actors, args)
    try:
        from io import BytesIO
        from PIL import Image, ImageDraw
    except ImportError as e:                             # Pillow absent (broken install)
        raise _SelectionExit(f"--layout breakdown needs Pillow, which failed to import: {e}")

    def _pane(*, annotations, focus, region) -> bytes:
        # No legend or overview names anywhere in the breakdown — the SCENE pane is a plain CSG map and
        # the per-actor panes are captioned. A tight `_BREAKDOWN_PAD`-px frame border keeps padding
        # minimal and CONSISTENT across panes (a fixed screen border, not a per-actor world margin).
        return preview.render_brushes_pgm(
            actors, view=view, size=size, annotations=annotations, iso_angle=args.iso_angle, region=region,
            highlight_polys=highlight_polys, highlight_points=highlight_points, color_by_csg=True,
            render_data=render_data, focus=focus, draw_legend=False, reserve_legend=False,
            brush_colors=brush_colors, frame_pad=_BREAKDOWN_PAD)

    # Pane 0: the whole scene in CSG — a plain spatial map, NO labels (actors are identified by their
    # own captioned panes below).
    panes = [("SCENE", _pane(annotations=preview.parse_annotation_spec("none"), focus=None, region=None))]
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
    grid = Image.new("RGB", (grid_w, grid_h), (245, 245, 245))
    draw = ImageDraw.Draw(grid)
    for i, (caption, ppm) in enumerate(panes):
        r, c = divmod(i, cols)
        x = c * (size + _BREAKDOWN_GAP)
        y = r * (cell_h + _BREAKDOWN_GAP)
        grid.paste(Image.open(BytesIO(ppm)).convert("RGB"), (x, y + _BREAKDOWN_CAPTION_H))
        draw.text((x + 4, y + 3), caption, fill=(0, 0, 0))
    n_brushes = sum(1 for a in actors if a.brush is not None)
    n_points = len(actors) - n_brushes
    print(f"breakdown: {n_brushes} brushes, {n_points} point actors, {n} panes, "
          f"{cols}x{rows} grid, {grid_w}x{grid_h} px", file=sys.stderr)
    if n > _BREAKDOWN_WARN_PANES:
        print(f"warning: --layout breakdown produced {n} panes — a large selection; consider a subset",
              file=sys.stderr)
    return grid          # a Pillow Image — the write boundary encodes it to PNG directly


def _render_actors_to_out(actors, args) -> int:
    show = _parse_show_set(getattr(args, "show", ""))    # validate ALWAYS (even a brush-only set)
    render_data = _preview_render_data(actors, args, show)
    factor = getattr(args, "frame_tightness", 0.8)
    if not 0.0 <= factor <= 1.0:                         # errors name the offending value (CLI rule)
        raise _SelectionExit(f"--frame-tightness must be in [0, 1], got {factor}")
    m = 16.0                                             # keep the target off the frame edge
    try:
        annotation_spec = preview.parse_annotation_spec(args.annotate)
        highlight_polys, highlight_points = _resolve_highlights(actors, args)
        focus = _resolve_focus(actors, args)
        explicit_region, frame_selector = _parse_frame(getattr(args, "frame", None))
        zoom_target = (_resolve_zoom(actors, frame_selector, render_data)
                       if frame_selector else None)
    except ValueError as e:                              # surface --annotate / selector parse failure
        raise _SelectionExit(str(e))
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
    layout = getattr(args, "layout", "quad")
    if layout == "breakdown":
        data = _render_breakdown_grid(actors, args, render_data=render_data)
    elif layout == "single":
        data = preview.render_brushes_pgm(actors, view=args.view, size=args.size,
                                          annotations=annotation_spec, iso_angle=args.iso_angle,
                                          region=region, highlight_polys=highlight_polys,
                                          highlight_points=highlight_points,
                                          color_by_csg=True, render_data=render_data, focus=focus,
                                          brush_colors=getattr(args, "brush_colors", "csg"))
    else:                                                # quad (default)
        data = preview.render_quad_pgm(actors, size=args.size, annotations=annotation_spec,
                                       iso_angle=args.iso_angle, region=region,
                                       highlight_polys=highlight_polys,
                                       highlight_points=highlight_points,
                                       color_by_csg=True, render_data=render_data, focus=focus,
                                       brush_colors=getattr(args, "brush_colors", "csg"))
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
            raise _SelectionExit(f"--out must name a file, not an existing directory: {requested}")
        # The extension the caller wrote is REPLACED by .png (the bytes are PNG, so the name must
        # say so). splitext strips only the final-basename extension -- NOT a dot in a parent dir
        # (e.g. --out /a/.cache/pic has no extension and must stay /a/.cache/pic.png).
        host_out = os.path.splitext(requested)[0] + ".png"
    else:
        fd, host_out = tempfile.mkstemp(prefix="uedctl-preview-", suffix=".png")
        os.close(fd)
    try:
        Path(host_out).parent.mkdir(parents=True, exist_ok=True)
        from io import BytesIO
        from PIL import Image
        img = data if isinstance(data, Image.Image) else Image.open(BytesIO(data))
        img.save(host_out)                                   # .png suffix -> Pillow writes PNG
    except ImportError as e:                                 # Pillow absent (broken install)
        raise _SelectionExit(f"writing the preview PNG needs Pillow, which failed to import: {e}")
    except OSError as e:                                     # unwritable path, decode failure, ...
        raise _SelectionExit(f"could not write preview to {host_out}: {e}")
    print(host_out)                     # the rendered HOST file path
    return 0


def _brush_actors_from(actors_t3d: dict, order: list[str], names: list[str], *,
                       brushes_only: bool = True):
    """The chosen actors parsed out of a stash/prefab T3D blob. `brushes_only` (the historical
    default, kept for any non-preview caller) drops point actors; preview passes False so point
    actors render too (they'd otherwise be silently dropped BEFORE the renderer)."""
    chosen = names or order
    level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen if n in actors_t3d)
                      + "\nEnd Map\n")
    return [level.actors[n] for n in chosen if n in level.actors
            and (not brushes_only or level.actors[n].brush)]


def _preview_stash(args, reg) -> int:
    actors_t3d, order, _pkgs, _meta, _folders = reg.read_stash(args.id)
    return _render_actors_to_out(
        _brush_actors_from(actors_t3d, order, args.names, brushes_only=False), args)


def _preview_from_t3d(args) -> int:
    """`actor preview --from-t3d <FILE…|->` — render every actor in the given snippet(s), NO level
    required. Multiple files concatenate in order; duplicate Names are uniquified so all render."""
    if args.names:
        raise _SelectionExit("--from-t3d is mutually exclusive with actor names (T3D mode "
                             "renders every actor in the snippet)")
    parsed = parse_t3d_actors(_read_t3d_files(args.from_t3d))
    seen: set[str] = set()
    for a in parsed:
        if a.name in seen:
            a.name = trunk.alloc_name(a.name.rstrip("0123456789") or a.name, seen)
        seen.add(a.name)
    return _render_actors_to_out(parsed, args)


def _texture_resolver(project):
    """A `utexture.TextureResolver` over the project's composed package files, or None when no
    config / no packages (a sprite then can't resolve → its actor degrades to a marker). MOCKABLE
    seam (tests patch it offline). Tolerant of a broken/absent games config (returns None)."""
    try:
        user_config = config.load_user_config()
        if user_config is None:
            return None
        files = config.composed_search_files(project, user_config)
    except config.ConfigError:
        return None
    if not files:
        return None
    return utexture.TextureResolver(files)


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
    `_class_defaults` seam) into a `preview.PointRender` + a list of stderr notes. May raise
    `uprops.SchemaError` (the caller degrades to an unscaled marker)."""
    defaults = _class_defaults(actor.cls, project)
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
        got = resolver.resolve_masked(bare) if (resolver and bare) else None
        if got is not None:
            w, h, rgb, mask = got
            fw, fh = preview.sprite_footprint(draw_scale, w, h)
            if fw > 0 and fh > 0:
                sprite = (w, h, rgb, mask)
                sprite_world = (fw, fh)
            else:                                     # DrawScale 0 / zero-size texture → no billboard
                notes.append(f"point actor {actor.name!r}: sprite {bare} has a zero footprint "
                             f"(DrawScale {draw_scale}) — drawing a marker")
        elif bare is None:
            notes.append(f"point actor {actor.name!r}: DT_Sprite with no Texture — drawing a marker")
        elif resolver is not None and resolver.exists(bare):
            notes.append(f"point actor {actor.name!r}: sprite {bare} is not P8-decodable — drawing "
                         "a marker (tracked: native non-P8 texture decoders)")
        else:
            notes.append(f"point actor {actor.name!r}: sprite texture {bare} not found — "
                         "drawing a marker")
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


def _preview_render_data(actors, args, show: set[str]) -> dict:
    """Resolve per-point-actor render data for the preview (dispatch owns schema/texture resolution;
    preview.py stays resolver-free). `show` is the validated `--show` member set. Brush actors are
    skipped (geometry needs no schema — a pure-brush preview works with no game install). A point actor
    whose schema is unresolvable degrades to an unscaled labelled marker + a one-line stderr note,
    NEVER a traceback."""
    point_actors = [a for a in actors if a.brush is None]
    if not point_actors:
        return {}
    show_collision = "collision" in show
    show_light = "light-range" in show
    show_sound = "sound-range" in show
    try:
        project = _resolve_project(args)
    except _ProjectError:
        project = None
    resolver = _texture_resolver(project)
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


def _apply_set(args, level_src, actors_t3d: dict, order: list[str], packages: list[str], *,
               default_group: str, anchor: list[str],
               folders: dict[str, str | None] | None = None) -> int:
    """Model-side merge of a captured actor set into the target trunk level via the `LevelSource`
    seam. Translate (--at → bbox-min corner, else the captured world `anchor`), allocate names, set
    Group, append to order. Validate all geometry up front (all-or-nothing at the write level). NO
    editor. Source-agnostic: the caller supplies `anchor` (stash from read_stash meta, prefab from
    read_prefab meta). Names are coordination-free random-suffix (decisions 2026-07-05 15:11,
    mirroring `actor add`); the trunk has no package manifest (the load set derives on demand at
    build, decisions 2026-06-30 18:47), so `packages` is not recorded.

    `folders` (name→folder|None) is each source member's STORED folder (persisted since the
    unify-T3D-trees change). It is the placement DEFAULT — a member lands in its stored folder;
    `--folder` OVERRIDES all placed actors (decisions 2026-07-18 addendum, sub-choice 2)."""
    from . import stashlib
    if not order:
        raise _SelectionExit("nothing to apply: source is empty")
    stored_folders = folders or {}
    main_level = level_src.load()
    src_level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in order
                                                    if n in actors_t3d) + "\nEnd Map\n")
    src = [src_level.actors[n] for n in order if n in src_level.actors]
    for a in src:                                       # re-attach each member's stored folder (a T3D
        a.folder = stored_folders.get(a.name)           # blob dropped it) as the placement default

    # `--at`/`anchor` anchor the bbox-min CORNER, not the actor Location (the documented contract).
    # Derive the delta from the source's ACTUAL world bbox-min so the placed corner lands exactly on
    # the target, regardless of whether the captured set is perfectly origin-normalized (actor_bounds
    # now honours MainScale/PostScale, so a scaled brush's bbox-min is its true scaled world corner).
    target = args.at if args.at is not None else tuple(Decimal(c) for c in anchor)
    src_lo, _src_hi = writes.union_bounds(src)
    delta = tuple(target[i] - src_lo[i] for i in range(3))
    group = None if getattr(args, "no_group", False) else (args.group or default_group)
    # `--folder` is an INDEPENDENT placement dimension from `--group` (spec §6): it stamps the
    # uedctl-side sidecar. Since the unify-T3D-trees change a member carries its STORED folder as the
    # default; an explicit `--folder` OVERRIDES it for every placed actor. The trunk always persists
    # it (apply's placement target is a trunk; the trunk-only restriction is on the folder VERBS, not
    # apply). Validate the override path AND every stored folder before any write (all-or-nothing).
    folder_override = getattr(args, "folder", None)
    if folder_override is not None:
        try:
            folderlib.validate_folder_path(folder_override)
        except ValueError as e:
            raise _SelectionExit(str(e))
    else:
        for f in {a.folder for a in src if a.folder is not None}:   # defensive: a hand-edited sidecar
            try:
                folderlib.validate_folder_path(f)
            except ValueError as e:
                raise _SelectionExit(f"stored folder in source: {e}")
    placed = []
    for a in stashlib.translate(src, delta):
        a = stashlib.with_group(a, group)
        if folder_override is not None:
            a = stashlib.with_folder(a, folder_override)
        # else: `with_group`/`translate` preserve the member's stored `folder` (the default)
        placed.append(a)
    for a in placed:                                    # all-or-nothing: validate before any write
        if a.brush is not None:
            validate_brush(a.brush)
    # Author-time gate on the captured set entering the trunk: existence-validate classes & textures
    # (usually already FQCN, so a cheap re-check — but covers a hand-edited stash/prefab box). Runs
    # after geometry validation, before any write (all-or-nothing).
    _validate_ingest_actors(placed, args)

    # alloc_name must see each prior placement, so add into main_level as we go and record once
    # with all touched names (M3: one apply = one commit, not N).
    existing_names = set(main_level.actors)
    placed_names: list[str] = []
    for a in placed:
        stem = a.name          # keep the name as-authored: `--base-name Pillar1` must stay `Pillar1_<rand>`
        a.name = trunk.alloc_name(stem, existing_names)         # random suffix; sees prior placements
        existing_names.add(a.name)
        main_level.actors[a.name] = a
        main_level.order = order_after_add(main_level.order, a.name)
        placed_names.append(a.name)
    rec_args = {"source": getattr(args, "id", None) or getattr(args, "name", None),
                "names": placed_names}
    level_src.save(verb="add", args=rec_args, level=main_level, touched=placed_names)
    for name in placed_names:                            # PRODUCER: placed names to stdout (feed `| verb -`)
        print(name)
    print(f"applied {len(placed)} actors", file=sys.stderr)
    return 0


def _prefab_root(args):
    """The prefab library root: the explicit `--prefab-dir` override, else the resolved project's
    `prefabs` dir (`uedctl.toml` `prefabs` key, default `<root>/prefabs/`). With neither a flag nor
    a project → clean `_ProjectError` exit 2 (spec 2026-07-17 §6 — the old repo-root/env fallback
    is retired, so prefab verbs outside a project need the flag)."""
    if getattr(args, "prefab_dir", None):
        return Path(args.prefab_dir)
    return Path(config.project_prefabs_dir(_resolve_project(args)))


def _promote_stash(args, reg) -> int:
    # No class/texture re-validation here: promote copies an already-validated stash blob-for-blob to
    # the prefab library, and the prefab is itself gated by `_validate_ingest_actors` when it is
    # `prefab apply`'d into a trunk — so nothing unvalidated can reach a trunk. Re-parsing the set
    # here just to re-check a validated set would be pure waste (spec: "may be dropped as redundant").
    from . import stashlib
    root = _prefab_root(args)
    actors_t3d, order, packages, meta, folders = reg.read_stash(args.id)
    try:
        stashlib.write_prefab(root, args.as_name, full_level=actors_t3d, order=order,
                              packages=packages, meta=meta, folders=folders, force=args.force)
    except (FileExistsError, ValueError) as e:
        raise _SelectionExit(str(e))
    return 0


def _brush_merge(args) -> int:
    """`brush intersect` / `brush deintersect` — CSG-merge a piped brush SET into ONE brush.

    A generator in the `brush build` mould: consumes T3D on stdin, produces one brush (or Mover)
    actor T3D on stdout, touches neither trunk nor stash.  The merge itself is
    `brushcsg.merge` -> `uedctl_native.intersect_brushset` (the decoded `bspBrushCSG` intersect
    tail); everything here is CLI shape — flag validation, placement, and the shared generator
    post-steps (`--prop`/`--rotate`/`--folder`/`--label`) that `brush build` also applies.
    """
    from . import brushcsg
    from .emit import emit_actor_t3d
    from .model import parse_t3d

    verb = args.sub
    deintersect = verb == "deintersect"
    mover_class = getattr(args, "mover_class", None)
    if mover_class is not None:
        parts = mover_class.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise _SelectionExit(
                f"brush {verb}: --mover-class must be Package.Name, got: {mover_class!r}")
        if args.csg is not None:
            raise _SelectionExit(f"brush {verb}: --csg is invalid with --mover-class "
                                 "(a mover does not participate in world CSG)")
        # `--solidity` is rejected outright on a mover — ALL values, `solid` included. A mover keeps
        # the SOURCE per-face solidity of the welded set, and that is always correct: a semisolid
        # face collides exactly like a solid one (only `nonsolid` is walk-through — collision spike
        # §3), so there is nothing to "scrub" and no reason to override. Actor-level solidity
        # (`semisolid`/`nonsolid`) is meaningless on a mover (it has no part in world CSG). Set a
        # mover's collision via --prop if you ever need to. (Earlier this special-cased `--solidity
        # solid` as a "cure" for a supposed semisolid-door-walk-through trap — that trap was a myth;
        # semisolid blocks.)
        if args.solidity is not None:
            raise _SelectionExit(
                f"brush {verb}: --solidity is invalid with --mover-class — a mover keeps the SOURCE "
                "per-face solidity of the welded set (a semisolid face blocks just like solid; only "
                "nonsolid is walk-through), so there is nothing to override. Set a mover's collision "
                "via --prop if needed.")
    try:
        origin = brushcsg.parse_anchor_spec(args.origin, flag="--origin", allow_keep=True)
        pivot_spec = brushcsg.parse_anchor_spec(args.pivot, flag="--pivot", allow_keep=False)
    except brushcsg.BrushCsgError as e:
        raise _SelectionExit(f"brush {verb}: {e}") from None
    # `--origin keep` is the RAW faithful form (Location=0, world-space verts) — it exists to diff
    # against an editor export, so it is incompatible with any placement (which would double-apply).
    if origin == "keep":
        if args.at is not None:
            raise _SelectionExit(
                f"brush {verb}: --at is invalid with --origin keep — `keep` emits the result at its "
                "absolute carved position (Location=0, world vertices), so placing it would "
                "translate it twice. Drop --origin keep to place the result")
        if pivot_spec is not None:
            raise _SelectionExit(
                f"brush {verb}: --pivot is invalid with --origin keep — `keep` emits the raw form "
                "with no local origin to pivot about")

    text = _read_t3d_input(args.set)
    if not text.strip():
        return 0                                          # empty stdin: clean no-op (exit 0)
    # `parse_t3d_actors` (NOT `parse_t3d`): the Name-keyed dict drops all but the LAST of each
    # duplicate group, and duplicates are the NORMAL case here — every `brush build cube` emits
    # `Name=Cube`, so the canonical composition (two generator outputs concatenated into one pipe)
    # feeds two identically-named actors and the additive would silently vanish. Keeping an ordered
    # list also makes STDIN ORDER (= the CSG order, load-bearing for a mixed add/subtract set)
    # explicit rather than incidental to dict insertion. Builder brushes are dropped as on every
    # other T3D ingest path: a `MAP EXPORT`-derived stream carries the transient red brush, and
    # `_oper_of` would otherwise merge it as an additive.
    actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    if not actors:
        raise _SelectionExit(
            f"brush {verb}: stdin held no brush actors — this reads a T3D SNIPPET (the output of "
            f"`actor show` / `stash show` / `brush build`), not the newline-separated NAME list "
            f"that `actor find` prints and the mutating verbs take")

    try:
        brushcsg.check_all_csg_brushes(actors, verb=verb,
                                       index=_mover_index(args, f"brush {verb}"))
        brushcsg.check_guards(actors, deintersect=deintersect)
        brushcsg.check_unscaled(actors)
        n = len(actors)
        print(f"brush {verb}: merging {n} brush{'' if n == 1 else 'es'}", file=sys.stderr)
        pairs = brushcsg.merge(actors, deintersect=deintersect)
    except brushcsg.BrushCsgError as e:
        raise _SelectionExit(str(e)) from None
    polys = [p for p, _src in pairs]
    if not polys:
        raise _SelectionExit(
            f"brush {verb}: the merge produced no faces — the set encloses no "
            f"{'void' if deintersect else 'solid'} against "
            f"{'a solid' if deintersect else 'an empty'} background")

    # A disjoint result stays ONE actor (there is deliberately no --split, decision 2026-07-24
    # 18:12); say so, since a caller wanting independent movers must re-run per subset.
    ncomp = brushcsg.component_count(polys)
    if ncomp > 1:
        print(f"brush {verb}: the result has {ncomp} DISCONNECTED components, emitted as one "
              f"actor — run the verb on each subset separately for independently movable pieces",
              file=sys.stderr)

    # `--texture` RETEXTURES the whole result. Without this the merge is faithful-only: each face
    # keeps the texture of the source face it was cut from (Phase-2 caps inherit the surrounding
    # brushes' surfaces), which is right by default but leaves no way to skin the welded brush —
    # and a door plug cut out of wall geometry comes out wearing the wall.
    if getattr(args, "texture", None):
        for p in polys:
            p.texture = args.texture
    poly_flags = brushcsg.apply_solidity(polys, args.solidity)
    if origin == "keep":
        location, prepivot = (Decimal(0), Decimal(0), Decimal(0)), (0, 0, 0)
    else:
        lo, hi = brushcsg.result_bounds(polys)
        anchor = brushcsg.resolve_anchor(origin, lo, hi)
        pivot = brushcsg.resolve_anchor(pivot_spec, lo, hi) if pivot_spec is not None else anchor
        location, prepivot = brushcsg.recenter(polys, anchor=anchor, pivot=pivot)
        if args.at is not None:
            location = tuple(args.at)                     # place the result's pivot at --at

    if mover_class is not None:
        name = args.base_name or mover_class.rsplit(".", 1)[-1]
    else:
        name = args.base_name or verb.capitalize()
    actor = brushcsg.make_result_actor(
        polys, name=name, location=location, prepivot=prepivot,
        csg=args.csg or "add", poly_flags=poly_flags, mover_class=mover_class)

    # The shared generator post-steps, in `brush build`'s order: --prop (schema-validated) first,
    # then --rotate (so it wins over a --prop Rotation=…), then the folder/label carriers.
    prop_tokens = getattr(args, "prop", None) or []
    if prop_tokens:
        try:
            ptoks = [propedit.parse_token(t, expect_value=True) for t in prop_tokens]
            plan = propedit.plan_edit(actor, ptoks, "set", _class_ctx(actor.cls, args),
                                      propedit.TYPED_FIELDS)
        except propedit.PropEditError as e:
            raise _SelectionExit(f"brush {verb}: {e}") from None
        except SchemaError as e:
            raise _SelectionExit(f"brush {verb}: {e}") from None
        actor.props = plan.props
        for attr, val in plan.typed_updates.items():
            setattr(actor, attr, val)
    _apply_generator_rotate([actor], getattr(args, "rotate", None))
    _apply_generator_org([actor], args)
    _validate_ingest_actors([actor], args)
    sys.stdout.write(emit_actor_t3d(actor))
    return 0



def _read_prefab_or_exit(root, name: str):
    """Read a prefab, converting a missing name, an OLD-format prefab, or a corrupt sidecar into a
    clean exit 2 instead of a traceback. Returns (full, order, packages, meta, folders). Callers must
    already have validated the name grammar (`validate_member_name`)."""
    from . import stashlib
    if name not in stashlib.list_prefabs(root):
        raise _SelectionExit(f"prefab not found: {name!r}")
    try:
        return stashlib.read_prefab(root, name)
    except stashlib.OldFormatPrefab as e:               # HARD CUTOVER: actionable, never a traceback
        raise _SelectionExit(str(e))
    except (OSError, ValueError) as e:                  # corrupt/unreadable per-actor tree or sidecar
        raise _SelectionExit(f"cannot read prefab {name!r}: {e}")


def _dispatch_prefab(args) -> int:
    """The durable tier-2 library. Reads (list/show/preview/drop) touch only the tracked dir;
    apply resolves the selected trunk level and reuses `_apply_set`."""
    from . import stashlib
    root = _prefab_root(args)
    # M1: validate the name before ANY filesystem touch (read OR the drop unlink) so a
    # `../../x` name can't escape the library root. validate_member_name raises ValueError;
    # surface it as a clean exit-2, not a traceback.
    if getattr(args, "name", None) is not None:
        try:
            stashlib.validate_member_name(args.name)
        except ValueError as e:
            raise _SelectionExit(str(e))
    if args.sub == "list":
        for name in stashlib.list_prefabs(root):
            print(name)
        return 0
    if args.sub == "show":
        actors_t3d, order, _pkgs, _meta, _folders = _read_prefab_or_exit(root, args.name)
        chosen = args.names or order
        if args.summary:
            level = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in chosen
                                                        if n in actors_t3d) + "\nEnd Map\n")
            print(stashlib.format_summary(args.name, [level.actors[n] for n in chosen
                                                     if n in level.actors]))
        else:
            print("\n".join(actors_t3d[n] for n in chosen if n in actors_t3d))
        return 0
    if args.sub == "preview":
        actors_t3d, order, _pkgs, _meta, _folders = _read_prefab_or_exit(root, args.name)
        return _render_actors_to_out(
            _brush_actors_from(actors_t3d, order, args.names, brushes_only=False), args)
    if args.sub == "drop":
        # A NEW prefab is a DIR `<name>/`; also unlink any OLD-format `<name>.t3d`/`.json` so a stale
        # pre-cutover prefab can still be dropped.
        dest = root / args.name
        if dest.is_dir():
            shutil.rmtree(dest)
        (root / f"{args.name}.t3d").unlink(missing_ok=True)
        (root / f"{args.name}.json").unlink(missing_ok=True)
        return 0
    if args.sub == "apply":
        level_src = _resolve_level_source(args)         # the trunk level (no project ⇒ clean exit 2)
        actors_t3d, order, packages, _meta, folders = _read_prefab_or_exit(root, args.name)
        # Prefab apply defaults to the ORIGIN (anchor=0), not the prefab's captured world bbox-min:
        # a shared prefab's original coords are meaningful only in its capture level, so without
        # --at it lands at the world origin. (stash apply keeps the captured anchor — paste-it-back
        # within the same level is the common case there.)
        return _apply_set(args, level_src, actors_t3d, order, packages,
                          default_group=Path(args.name).name,           # basename, never slashed path
                          anchor=["0", "0", "0"], folders=folders)
    raise _SelectionExit(f"unimplemented prefab sub-verb: {args.sub}")


def _dispatch_texture(args) -> int:
    """The offline texture catalog. STATELESS — no level, no live editor read/edit. `sync`
    mints a per-command ephemeral container for UCC batchexport only; every other verb is pure
    manifest I/O.

    Project-scoped: the catalog dir defaults to the resolved project's `catalog` dir
    (`config.project_catalog_dir`, default `<root>/texture-catalog/`) and `sync` discovers
    packages from the composed config search path (project overlay shadows game base), NOT the
    retired hardcoded `substrate_code_dirs`/`texture_catalog_root` (Andrzej's directive, decisions.md
    2026-07-14 — texture sync onto the composed project+game path). The project is resolved LAZILY:
    `sync` always needs it (for discovery); every OTHER verb — reads AND `classify set` — needs it
    only to default the catalog dir, so an explicit `--catalog-dir` runs OUTSIDE a project (the
    per-package flock is catalog-adjacent, `<catalog>/.locks/`, not project-derived — decision
    2026-07-18)."""
    from . import texture, texture_catalog as tc

    _project = {}
    def project() -> config.Project:                     # resolve once, only when actually needed
        if "p" not in _project:
            _project["p"] = _resolve_project(args)       # no project ⇒ _ProjectError → exit 2
        return _project["p"]

    catalog_dir = args.catalog_dir or config.project_catalog_dir(project())

    def lock_dir() -> str:
        """`<catalog>/.locks/` — the per-package flock home, derived from the CATALOG DIR it
        guards, not the project (decision 2026-07-18): every writer to one catalog shares one lock
        domain even across projects/checkouts pointing at the same shared catalog, and an explicit
        `--catalog-dir` needs no project for ANY texture verb (restores spec §6's override
        contract for `classify set`). Self-ignoring like `.uedctl/` — lock litter can never be
        committed from a tracked catalog dir."""
        return str(config.self_ignoring_dir(Path(catalog_dir) / ".locks", create=True,
                                            what="catalog lock dir"))

    def _load_all() -> list[tc.Manifest]:
        d = Path(catalog_dir)
        out = []
        for jf in sorted(d.glob("*.json")) if d.is_dir() else []:
            try:
                if (m := tc.load_manifest(jf)) is not None:
                    out.append(m)
            except (ValueError, OSError) as e:
                print(f"skipping unreadable manifest {jf}: {e}", file=sys.stderr)
        return out

    if args.sub == "sync":
        # Discovery is config-driven (Andrzej's directive, decisions.md 2026-07-14): EVERY package on
        # the composed project+game search path (project overlay shadows game base, stem-deduped by
        # `composed_search_files`) — including `.u` code packages, because a `.u` is the same Unreal
        # package format and can hold textures too (DeusEx skins live in `DeusExItems.u`). A package
        # with no textures just batchexports nothing and is skipped. The build container mounts the
        # WHOLE composed dir set at `/resources/<n>` (one uniform scheme) so every discovered package
        # is reachable by bare name via its crafted `[Core.System] Paths`.
        user_config = config.load_user_config()
        if user_config is None:                          # hard error — decision 2026-07-06 05:12
            raise _ProjectError(
                "no per-user games config (~/.uedctl/config.toml): texture sync needs the game's "
                "base package paths; create it with a [games.<name>] paths dir list")
        # (bare_name, host_file) for EVERY package on the composed path, stem-deduped
        # project-shadows-base by composed_search_files.
        all_pkgs = [(config.pkg_stem(p), p)
                    for p, _prov in config.composed_search_files(project(), user_config)]
        search_dirs = config.composed_search_dirs(project(), user_config)
        mounts = container_assets.resource_mounts(search_dirs)   # one uniform set: all reachable
        if args.package:
            want = args.package.casefold()
            pkgs = [(n, p) for n, p in all_pkgs if n and n.casefold() == want]
            if not pkgs:
                raise _SelectionExit(
                    f"package not found on the composed search path: {args.package}")
        else:
            pkgs = [(n, p) for n, p in all_pkgs if n]
        images_root = str(config.texture_images_root())
        if not pkgs:
            print("no packages found on the composed search path", file=sys.stderr)
            return 2
        # batchexport runs offline UCC in a container. Editors are per-command ephemeral (no
        # standing container, no `--container` flag), so mint ONE no-GUI container for the whole
        # sweep and tear it down after.
        from .stub import ephemeral_build_container, StubBuildError
        built = 0
        try:
            with ephemeral_build_container(mounts=mounts,
                                           state_dir=config.state_dir(project().root, create=True)
                                           ) as container:
                for name, file_path in pkgs:
                    try:
                        m = tc.sync_package(package=name, package_file=file_path, container=container,
                                            catalog_dir=catalog_dir, images_root=images_root,
                                            force=args.force, batchexport=texture.batchexport_textures,
                                            lock_dir=lock_dir())
                    except (subprocess.CalledProcessError, OSError, ValueError) as e:
                        print(f"{name}: skipped ({e})", file=sys.stderr)   # one bad package never aborts
                        continue
                    if m is not None:
                        built += 1
                        print(f"{name}: {len(m.textures)} textures")
        except StubBuildError as e:                    # container couldn't start (docker down / image)
            print(f"texture sync: could not start build container: {e}", file=sys.stderr)
            return 2
        if built == 0:
            # Discovery + batchexport ran; nothing produced textures (none on the container Paths,
            # per the v1 limit) — a NORMAL outcome, not a misconfiguration. rc 0.
            print(f"discovered {len(pkgs)} packages; none produced textures "
                  f"(none on the container Paths)", file=sys.stderr)
        return 0

    if args.sub == "list":
        state = next((s for s in ("unclassified", "classified", "stale", "removed")
                      if getattr(args, s)), None)
        for m in _load_all():
            if args.package and m.package.lower() != args.package.lower():
                continue
            for e in m.textures.values():
                if state and tc.bucket(e) != state:
                    continue
                print(f"{e.ref}\t{e.width}x{e.height}\t{tc.bucket(e)}\t{','.join(e.tags)}")
        return 0

    if args.sub == "search":
        if not args.query and not args.tag and not args.color:
            raise _SelectionExit("search needs a query or --tag/--color")
        try:
            tc.validate_colors([c.lower() for c in args.color])
        except ValueError as e:
            raise _SelectionExit(str(e))
        refs = tc.search(_load_all(), args.query, tags=args.tag, colors=args.color,
                         package=args.package)
        if not refs:
            # No match is a NORMAL outcome (rc 0): stdout stays empty so a pipe into
            # `poly set` is clean; the "no matches" note goes to stderr.
            print("no matches", file=sys.stderr)
            return 0
        for r in refs:
            print(r)
        return 0

    if args.sub == "tags":
        for tag, n in tc.all_tags(_load_all(), package=args.package):
            print(f"{tag}\t{n}")
        return 0

    if args.sub == "classify" and args.csub == "status":
        manifests = [m for m in _load_all()                  # load ONCE (atomic snapshot + cheaper)
                     if not args.package or m.package.lower() == args.package.lower()]
        counts = tc.status_counts(manifests)
        for pkg, c in sorted(counts["per_package"].items()):
            print(f"{pkg}\ttotal {c['total']}\tclassified {c['classified']}\t"
                  f"unclassified {c['unclassified']}\tstale {c['stale']}\tremoved {c['removed']}")
        g = counts["total"]
        print(f"TOTAL\t{g['total']} / {g['classified']} classified")
        if args.full:
            for m in manifests:
                for e in m.textures.values():
                    if tc.bucket(e) in ("unclassified", "stale"):
                        print(e.ref)
        return 0

    if args.sub == "classify" and args.csub == "set":
        pkg = args.ref.split(".", 1)[0]
        mpath = tc.manifest_path(catalog_dir, pkg)
        with tc._package_lock(lock_dir(), pkg):
            try:
                m = tc.load_manifest(mpath)               # corrupt catalog JSON → ValueError, caught below
                if m is None:
                    raise _SelectionExit(
                        f"no catalog for package: {pkg} — run 'texture sync --package {pkg}'")
                out = tc.classify_set(m, args.ref, tags=args.tags, description=args.description,
                                      colors=args.colors)
                tc.save_manifest(mpath, out)
            except (ValueError, OSError) as e:
                raise _SelectionExit(f"{args.ref}: {e}")
        print(args.ref)
        return 0

    raise _SelectionExit(f"unimplemented texture sub-verb: {args.sub}")


def _dispatch_substrate(args) -> int:
    """Substrate build utilities. `substrate stub <pkg>` converts a v68 code package into a v69
    stub `.u` (explicit escape hatch; the lazy auto-trigger is the resolution hook). STATELESS.
    Project-scoped: the v68 SOURCE + content deps come from the composed config CODE/CONTENT dirs
    (decisions.md 2026-07-14 — config-drive stub source), so it needs a resolved project + games
    config, exactly like `level materialize`."""
    if args.sub != "stub":
        raise _SelectionExit(f"unimplemented substrate sub-verb: {args.sub}")
    from . import stub, container_assets
    from .stub_cache import list_manifests

    if args.list:
        for m in list_manifests(config.stub_cache_root()):
            print(f"{m.file}\t{m.built_at}")
        return 0
    if not args.package:
        print("substrate stub: a package name is required (or use --list)", file=sys.stderr)
        return 2
    project = _resolve_project(args)                     # no project ⇒ _ProjectError → exit 2
    user_config = config.load_user_config()
    if user_config is None:                              # hard error — decision 2026-07-06 05:12
        raise _ProjectError(
            "no per-user games config (~/.uedctl/config.toml): substrate stub needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = container_assets.resource_mounts(search_dirs)
    try:
        with stub.ephemeral_build_container(mounts=mounts,
                                            state_dir=config.state_dir(project.root, create=True)
                                            ) as container:
            path = stub.ensure_stub(args.package, container=container, search_dirs=search_dirs,
                                    mounts=mounts, force=args.force)
    except (RuntimeError, ValueError) as e:   # StubBuild/StubClosure + parse_header unsupported-version
        print(f"substrate stub {args.package}: {e}", file=sys.stderr)
        return 2
    print(path)
    return 0


class _SelectionExit(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _dispatch_mover_key(args, src) -> int:
    from . import movers, rotation
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        raise _SelectionExit(f"mover key {args.keysub}: {e.args[0]}")
    actor = level.actors[canonical]
    if not movers.is_mover(actor, _mover_index(args, f"mover key {args.keysub}")):
        raise _SelectionExit(
            f"mover key {args.keysub}: {canonical} is not a Mover "
            f"(class {actor.cls or '(none)'} does not descend from {movers.MOVER_BASE})")

    if args.keysub == "list":
        if getattr(args, "json", False):
            import json
            print(json.dumps(query.list_mover_keys(actor), indent=2))
        else:
            print(query.format_mover_keys(actor))
        return 0

    if args.keysub == "count":
        if args.n is None:                       # getter: print the current count to stdout
            print(movers.num_keys(actor))
            return 0
        try:
            movers.set_num_keys(actor, args.n)   # shared bounded setter (== `actor prop set NumKeys=`)
        except ValueError as e:
            raise _SelectionExit(str(e)) from None
        src.save(verb="mover-key-count",
                 args={"name": canonical, "num_keys": movers.num_keys(actor)},
                 level=level, touched=[canonical])
        return 0

    if args.keysub in ("move", "rotate"):
        # Frame / --by gating runs BEFORE the index guard (spec 2026-07-20). argparse already
        # forbids --from-base WITH --from-world and requires exactly one of --to/--by.
        from_base = getattr(args, "from_base", False)
        from_world = getattr(args, "from_world", False)
        if args.to is not None and not (from_base or from_world):
            raise _SelectionExit(
                f"mover key {args.keysub}: --to needs a coordinate frame — "
                "choose --from-base (offset from the base pose) or --from-world (absolute world)")
        if args.by is not None and (from_base or from_world):
            raise _SelectionExit(
                f"mover key {args.keysub}: --by is a frame-agnostic delta — "
                "drop --from-base/--from-world (they apply only to --to)")
        n = movers.num_keys(actor)
        if args.index == 0:
            verb = "actor move" if args.keysub == "move" else "actor rotate --by"
            raise _SelectionExit(
                f"mover key {args.keysub}: key 0 is the base pose — use '{verb}' on the mover")
        if not (1 <= args.index < n):
            raise _SelectionExit(
                f"mover key {args.keysub}: {canonical} has no key {args.index} "
                f"(keys 1..{n-1}) — raise the count first with 'mover key count {canonical} <n>'")
        if args.keysub == "move":
            cur = movers.key_pos(actor, args.index)
            if args.to is not None:
                if from_base:
                    new = tuple(args.to)                 # offset written straight into KeyPos
                else:                                    # --from-world: subtract the base pose
                    base = actor.location or (Decimal(0), Decimal(0), Decimal(0))
                    new = tuple(args.to[j] - base[j] for j in range(3))
            else:
                new = tuple(cur[j] + args.by[j] for j in range(3))
            movers.set_key_pos(actor, args.index, new)
            rec = {"name": canonical, "index": args.index,
                   "key_pos": movers.emit_or_none_pos(actor, args.index)}
        else:  # rotate
            cur_uu = movers.key_rot(actor, args.index)
            delta_uu = tuple(rotation.uu_field(c) for c in (args.to or args.by))
            if args.to is not None:
                if from_base:
                    new_uu = delta_uu                    # offset UU written straight into KeyRot
                else:                                    # --from-world: FRotator field-subtract base
                    base_uu = rotation.actor_rotation_uu(actor)
                    new_uu = rotation.subtract_uu(delta_uu, base_uu)
            else:
                new_uu = rotation.compose_uu(cur_uu, delta_uu)
            movers.set_key_rot(actor, args.index, new_uu)
            rec = {"name": canonical, "index": args.index,
                   "key_rot": movers.emit_or_none_rot(actor, args.index)}
        src.save(verb=f"mover-key-{args.keysub}", args=rec,
                        level=level, touched=[canonical])
        return 0

    if args.keysub == "remove":
        n = movers.num_keys(actor)
        if args.index == 0:
            raise _SelectionExit("mover key remove: key 0 is the base pose — delete the actor "
                                 "with 'actor delete' to remove the whole mover")
        if not (1 <= args.index < n):
            raise _SelectionExit(
                f"mover key remove: {canonical} has no key {args.index} (keys 1..{n-1})")
        if n - 1 < movers.MIN_KEYS:
            raise _SelectionExit(
                f"mover key remove: a mover needs at least {movers.MIN_KEYS} keys")
        movers.remove_key(actor, args.index)
        src.save(verb="mover-key-remove",
                        args={"name": canonical, "index": args.index},
                        level=level, touched=[canonical])
        return 0

    raise _SelectionExit(f"mover key: unimplemented sub-verb: {args.keysub}")


class _ProjectError(Exception):
    """No uedctl project could be resolved — user-facing (→ stderr + exit 2)."""


def _resolve_project(args) -> config.Project:
    """Resolve the current project (--project > UEDCTL_PROJECT > walk-up from cwd to the nearest
    `uedctl.toml`). Errors clearly if none is found — every level/content verb needs a project. On
    the failure path only, a cheap child-dir scan detects a RETIRED old-layout project
    (`<child>/config.toml`) and names the migration (spec 2026-07-17 §8)."""
    proj = config.resolve_project(
        project_flag=getattr(args, "project", None),
        env_project=os.environ.get("UEDCTL_PROJECT"),
        cwd=os.getcwd(),
    )
    if proj is None:
        msg = ("not in a uedctl project (no uedctl.toml found here or above); "
               "pass --project <root>")
        old = config.find_old_layout_project_dir(os.getcwd())
        if old:
            parent = os.path.dirname(old)
            msg += (f"\nfound old-layout project dir {old}/ — this layout is retired; move its "
                    f"config.toml to {os.path.join(parent, 'uedctl.toml')} (see docs) and delete "
                    f"its tmp/")
        raise _ProjectError(msg)
    return proj


class TrunkLevelSource:
    """Git-native level source: the on-disk T3D trunk `maps/<level>/`. Holds the actors' order_values
    between load and save so a mutation preserves every surviving actor's rank and mints one (after all
    of them) for a newly-added actor. `save(ranks=…)` is the CSG-order OVERRIDE channel by which
    `actor order`/`actor add --order` reassign or off-append a rank (spec 2026-07-18 §3)."""
    kind = "level"                                       # uniform box label (level status / doctor)
    # True only when this source was resolved from the ambient $UEDCTL_LEVEL (not an explicit
    # `--tree`). A mutation (`save`) then echoes the level once to stderr — the visibility guard
    # against editing the wrong level via a stale export (decisions 2026-07-20). Class default so a
    # directly-constructed source (materialize/preview build one) is silent unless it opts in.
    from_env = False

    def __init__(self, trunk_dir: Path):
        self.trunk_dir = Path(trunk_dir)
        self._ranks: dict[str, str] = {}
        self._loaded_names: set[str] = set()
        self._loaded_bodies: dict[str, str] = {}
        self._loaded_folders: dict[str, str | None] = {}
        self._loaded_labels: dict[str, frozenset[str]] = {}
        self._loaded = False
        self._announced = False                          # echo the from_env level at most once

    @property
    def display_name(self) -> str:
        return self.trunk_dir.name

    def load(self) -> Level:
        (level, self._ranks, self._loaded_bodies,
         self._loaded_folders) = trunk.read_level_with_bodies(self.trunk_dir)
        # Labels ride on `level.actors[name].labels` (read_actor_tree loads the sidecar there, not
        # into the returned tuple), so derive the baseline from the model — same as folders.
        self._loaded_labels = {n: level.actors[n].labels for n in level.actors}
        self._loaded_names = set(self._ranks)           # the on-disk set THIS process saw at load
        self._loaded = True
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # verb/args/touched ignored — git is the history; packages derive on demand at build.
        # `ranks` is the CSG-order OVERRIDE channel (spec 2026-07-18 §3): a name present in it takes
        # the override value instead of the default rule below — the ONLY way a `Level` (which carries
        # no per-actor order_value) can move an existing actor's rank (`actor order`) or place a new
        # one off the append point (`actor add --order`). It flows straight into `write_level`, and
        # the `changed` diff below fires because the override differs from the UNTOUCHED `self._ranks`
        # snapshot — so we must NOT mutate `self._ranks` before the write, or the diff self-cancels.
        if not self._loaded:                            # guard the whole-level re-rank footgun
            raise RuntimeError("TrunkLevelSource.save requires a prior load() (it preserves the "
                               "existing order_values)")
        # Visibility guard (decisions 2026-07-20): a trunk WRITE resolved from the ambient
        # $UEDCTL_LEVEL announces the level once, so a stale export can't silently edit the wrong
        # one. save() is the actual mutation seam — reads never reach here, so this is self-limiting
        # to writes without any per-verb enumeration. Explicit `--tree` leaves from_env False (silent).
        if self.from_env and not self._announced:
            _announce_env_level(self.display_name)
            self._announced = True
        override = ranks or {}
        resolved: dict[str, str] = {}
        for name in level.order:
            # membership test, not truthiness, so a legit empty stored rank is preserved not re-minted;
            # rank a new actor after the union of ALL existing + already-assigned ranks (never a partial
            # max) so it can't collide with a not-yet-emitted actor.
            if name in override:
                resolved[name] = override[name]
            else:
                resolved[name] = (self._ranks[name] if name in self._ranks
                                  else trunk.append_rank({**self._ranks, **resolved}))
        ranks = resolved
        # DELTA write under a short per-level flock (decisions.md 2026-07-18 — concurrent trunk
        # writers): write ONLY the actors whose body or rank differs from THIS process's load
        # snapshot (content-diff, not `touched` — robust to any verb under-reporting), and prune
        # ONLY this process's own deletions (loaded set minus current set). An actor another
        # process added, edited, or deleted meanwhile is therefore never stomped/resurrected from
        # our stale model — disjoint concurrent edits compose (equal freshly-minted order_values
        # stay harmless via the name tiebreak, decisions 2026-07-05 15:11). The flock serializes
        # savers so one saver's prune/replace can never race another mid-write. Resource-adjacent
        # like the catalog locks: `<maps-dir>/.locks/`, self-ignoring.
        deleted = self._loaded_names - set(level.actors)
        new_bodies = {name: trunk.dump_actor_body(actor) for name, actor in level.actors.items()}
        # The changed set fires on a body, rank, OR FOLDER delta vs the load snapshot. Folder is a
        # sidecar (not in the body), so a folder-ONLY change — INCLUDING `"x"`→None (unset) — leaves
        # body+rank identical; without this comparison the write is silently dropped (spec §2 trap).
        changed = {name for name, body in new_bodies.items()
                   if body != self._loaded_bodies.get(name)
                   or ranks[name] != self._ranks.get(name)
                   or level.actors[name].folder != self._loaded_folders.get(name)
                   or level.actors[name].labels != self._loaded_labels.get(name, frozenset())}
        lock_home = config.self_ignoring_dir(self.trunk_dir.parent / ".locks", create=True,
                                             what="trunk lock dir")
        with open(lock_home / f"level-{self.trunk_dir.name}.lock", "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            trunk.write_level(self.trunk_dir, level, ranks, deleted=deleted, only=changed)
        self._ranks = ranks
        self._loaded_names = set(level.actors)
        self._loaded_bodies = new_bodies                # the written state is the next diff baseline
        self._loaded_folders = {name: actor.folder for name, actor in level.actors.items()}
        self._loaded_labels = {name: actor.labels for name, actor in level.actors.items()}


class StashLevelSource:
    """A stash register entry (`--tree stash/<id>`) as a `LevelSource`. Mirrors
    `TrunkLevelSource`'s `load()`/`save(*, verb, args, level, touched)` seam so every content verb
    edits a stash exactly as it edits the trunk. Stash/prefab use a flat `order` list (no per-actor
    `order_value` sidecar), so `_ranks` is empty — no content verb reads it (only `level
    status`/`doctor` do, and those are level-only). `save` recomputes the texture-only `packages`
    from the edited actors and preserves `meta` (the capture anchor); `write_stash(force=True)` swaps
    atomically."""
    kind = "stash"                                       # uniform box label (level status / doctor)
    from_env = False                                     # a box is never the ambient env level (attr parity)

    def __init__(self, reg: "stash_register.FileStashRegister", stash_id: str):
        self.reg = reg
        self.id = stash_id
        self._ranks: dict[str, str] = {}
        self._meta: dict = {}

    @property
    def display_name(self) -> str:
        return self.id

    def load(self) -> Level:
        try:
            blobs, order, _pkgs, self._meta, folders = self.reg.read_stash(self.id)
        except (OSError, ValueError) as e:               # corrupt meta.json/state → clean, not a traceback
            raise _SelectionExit(f"cannot read stash {self.id!r}: {e}")
        # `if n in blobs` guards a stored order that names a missing blob (never a bare KeyError).
        keep = [n for n in order if n in blobs]
        level = parse_t3d("Begin Map\n" + "\n".join(blobs[n] for n in keep) + "\nEnd Map\n")
        level.order = keep
        for n in keep:                                   # re-attach each member's stored folder (a
            level.actors[n].folder = folders.get(n)      # T3D blob drops it) so an edit preserves it
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # `ranks` (the CSG-order override) is IGNORED here: the ordering verbs reject a stash target
        # before ever reaching this save (the internal order_value sidecar is not exposed to them), so
        # a real override never arrives. Folders ARE preserved (persisted per member since the
        # unify-T3D-trees change) so an edit that doesn't touch a member's folder keeps it.
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order if n in level.actors}
        folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
        self.reg.write_stash(
            self.id, full_level=full, order=[n for n in level.order if n in level.actors],
            packages=sorted(stashlib.referenced_packages(list(level.actors.values()))),
            meta=self._meta, folders=folders, force=True)


class PrefabLevelSource:
    """A durable prefab library entry (`--tree prefab/<name>`) as a `LevelSource`. Same shape as
    `StashLevelSource` but backed by `stashlib.read_prefab`/`write_prefab` — a per-actor T3D tree
    `<name>/{actors/…, packages, meta.json}` (unify-T3D-trees, decisions 2026-07-18 23:01 UTC). The
    split-sibling `meta.json` holds ONLY the capture extras (`anchor`/`ts`), so passing it straight
    back to `write_prefab` cannot clobber the fresh order/packages (they are the sidecar/order_value
    files now, not JSON keys)."""
    kind = "prefab"                                      # uniform box label (level status / doctor)
    from_env = False                                     # a box is never the ambient env level (attr parity)

    def __init__(self, root: Path, name: str):
        self.root = Path(root)
        self.name = name
        self._ranks: dict[str, str] = {}
        self._meta: dict = {}

    @property
    def display_name(self) -> str:
        return self.name

    def load(self) -> Level:
        try:
            blobs, order, _pkgs, self._meta, folders = stashlib.read_prefab(self.root, self.name)
        except stashlib.OldFormatPrefab as e:            # HARD CUTOVER: actionable, never a traceback
            raise _SelectionExit(str(e))
        except (OSError, ValueError) as e:               # corrupt per-actor tree/sidecar → clean, not a traceback
            raise _SelectionExit(f"cannot read prefab {self.name!r}: {e}")
        keep = [n for n in order if n in blobs]
        level = parse_t3d("Begin Map\n" + "\n".join(blobs[n] for n in keep) + "\nEnd Map\n")
        level.order = keep
        for n in keep:                                   # re-attach each member's stored folder
            level.actors[n].folder = folders.get(n)
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # `ranks` (the CSG-order override) is IGNORED here: the ordering verbs reject a prefab target
        # (the internal order_value sidecar is not exposed to them). Folders ARE preserved per member.
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order if n in level.actors}
        folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
        stashlib.write_prefab(
            self.root, self.name, full_level=full,
            order=[n for n in level.order if n in level.actors],
            packages=sorted(stashlib.referenced_packages(list(level.actors.values()))),
            meta=self._meta, folders=folders, force=True)


def _resolve_level_source(args):
    """The level source for this invocation. Default (no `--tree`): the ambient `$UEDCTL_LEVEL` level
    on the git-native trunk — the env fallback marks the returned source `from_env=True`, so a
    subsequent mutation echoes which level it edited (the visibility guard against a stale export —
    decisions 2026-07-20). With `--tree KIND/NAME` (KIND ∈ level|stash|prefab): the named box
    EXPLICITLY — a `StashLevelSource`, `PrefabLevelSource`, or a `TrunkLevelSource` on a NAMED level's
    trunk (no echo; the user named the target). `config.resolve_project` returns None (→ our clean
    `_ProjectError`) for a missing project, though a bare-NAME `--project` still raises
    `config.ConfigError` (a hard user error, caught by `dispatch()` → exit 2)."""
    tgt = getattr(args, "tree", None)
    if tgt is not None:                                  # explicit --tree (incl. "" → a clear error,
        kind, sep, name = tgt.partition("/")             # not a silent fallback to the ambient level)
        if not sep or kind not in ("level", "stash", "prefab") or not name:
            raise _SelectionExit(
                f"--tree must be KIND/NAME (KIND ∈ level|stash|prefab), got {tgt!r}")
        # MANDATORY before constructing any source: read_stash/read_level do NOT validate the top
        # name, so `--target stash/../../x` would otherwise escape on both load AND the later save.
        try:
            stashlib.validate_member_name(name)
        except ValueError as e:
            raise _SelectionExit(str(e))
        project = _resolve_project(args)                 # all three boxes live under the project
        if kind == "stash":
            reg = _stash_register_for(project)
            if not reg.exists(name):                     # meta.json-keyed (nested + emptied-safe)
                raise _SelectionExit(f"stash not found: {name!r}")
            return StashLevelSource(reg, name)
        if kind == "prefab":
            root = _prefab_root(args)
            if name not in stashlib.list_prefabs(root):
                raise _SelectionExit(f"prefab not found: {name!r}")
            return PrefabLevelSource(root, name)
        # kind == "level": a NAMED level's trunk (edit a level without exporting $UEDCTL_LEVEL).
        # Levels are SINGLE safe segments (unlike nested stash/prefab names) — `validate_member_name`
        # allows `/`, so re-check here: a nested/dotted name would scatter lock homes or edit the
        # self-ignored `maps/.locks/` as a level (review fix, 2026-07-18).
        try:
            level_select._check_safe_level(name)
        except level_select.LevelSelectionError as e:
            raise _SelectionExit(str(e))
        maps_dir = Path(config.project_maps_dir(project))
        if not (maps_dir / name).is_dir():
            raise _SelectionExit(f"level not found: {name!r}")
        return TrunkLevelSource(maps_dir / name)         # explicit --tree → from_env stays False (no echo)

    # No --tree: the ambient $UEDCTL_LEVEL (decisions 2026-07-20 — env passed IN, mirroring
    # config.resolve_project). A missing/blank/malformed value raises LevelSelectionError → exit 2.
    project = _resolve_project(args)                     # no project → _ProjectError → exit 2
    maps_dir = Path(config.project_maps_dir(project))
    name = level_select.resolve_level(env_level=os.environ.get("UEDCTL_LEVEL"), maps_dir=maps_dir)
    src = TrunkLevelSource(maps_dir / name)
    src.from_env = True                                  # env fallback → a mutation announces the level
    return src


def _announce_env_level(name: str, *, action: str = "editing") -> None:
    """Echo the ambient level to STDERR (pipe-safe — the CLI ethos routes human notes there) when a
    mutating verb resolved it from `$UEDCTL_LEVEL` rather than an explicit `--tree`. The visibility
    guard against a stale export silently hitting the wrong level (decisions 2026-07-20). `action` is
    the verb-appropriate word: `editing` (trunk write), `materializing` (build), `capturing from`."""
    print(f"{action} level {name!r} (from $UEDCTL_LEVEL)", file=sys.stderr)


def _resolve_level_only(args, *, verb: str, alt_hint: str | None = None) -> tuple[str, bool]:
    """Resolve the level for a build/preview verb that operates on a LEVEL only (materialize, preview
    trunk mode). Same precedence as `_resolve_level_source` (explicit `--tree` > ambient
    `$UEDCTL_LEVEL`) but constrained to the `level` kind — `--tree stash|prefab` is rejected with a
    clear exit 2, since a captured actor-set has no world to build or walk (dedicated `stash preview`/
    `prefab preview` exist). Returns `(level_name, from_env)`; the caller uses the name to build a
    `TrunkLevelSource` and `from_env` to decide whether to announce the level."""
    project = _resolve_project(args)                     # no project → _ProjectError → exit 2
    maps_dir = Path(config.project_maps_dir(project))
    tgt = getattr(args, "tree", None)
    if tgt is not None:                                  # explicit --tree (incl. "" → clear error)
        kind, sep, name = tgt.partition("/")
        if not sep or kind not in ("level", "stash", "prefab") or not name:
            raise _SelectionExit(
                f"--tree must be KIND/NAME (KIND ∈ level|stash|prefab), got {tgt!r}")
        if kind != "level":
            msg = f"{verb} operates on a level, not --tree {kind}/…"
            if alt_hint:
                msg += f"; {alt_hint}"
            raise _SelectionExit(msg)
        try:
            level_select._check_safe_level(name)         # single safe segment (nested/dotted → error)
        except level_select.LevelSelectionError as e:
            raise _SelectionExit(str(e))
        if not (maps_dir / name).is_dir():
            raise _SelectionExit(f"level not found: {name!r}")
        return name, False                               # explicit → no echo
    name = level_select.resolve_level(env_level=os.environ.get("UEDCTL_LEVEL"), maps_dir=maps_dir)
    return name, True                                    # ambient → caller may echo


def _stash_register_for(project) -> "stash_register.FileStashRegister":
    """The project's stash register at `<root>/.uedctl/stash/` — machine-local scratch in the
    self-ignoring state dir (created, with its `*` .gitignore, on first use). The ONE builder both
    stash-register consumers (`_resolve_stash_register` and `_resolve_level_source`'s
    `--tree stash/NAME` branch) go through."""
    return stash_register.FileStashRegister(
        config.state_subdir(project.root, "stash", create=True))


def _resolve_stash_register(args) -> "stash_register.FileStashRegister":
    """The stash register for the resolved project (`<root>/.uedctl/stash/`). Exposes
    `write_stash`/`read_stash`/`list_stashes`/`drop_stash` for `_dispatch_stash`."""
    return _stash_register_for(_resolve_project(args))   # raises _ProjectError → exit 2


def _level_actor_counts(level: Level) -> tuple[int, int, int]:
    """(total, brush actors, point actors) for the level."""
    total = len(level.actors)
    brushes = sum(1 for a in level.actors.values() if a.brush is not None)
    return total, brushes, total - brushes


def _warn_duplicate_point_locations(level, added_names: list[str]) -> None:
    """Point actors (no brush) silently accept a shared Location — each still gets a unique Name, so
    two decorations dropped on the same spot is invisible. Warn (stderr) when 2+ point actors, at
    least one of them just added, share a Location. Cheap, advisory; never blocks the add."""
    added = set(added_names)
    by_loc: dict[tuple, list[str]] = {}
    for name, a in level.actors.items():
        if a.brush is not None or a.location is None:   # brushes / location-less actors don't count
            continue
        by_loc.setdefault(tuple(a.location), []).append(name)
    for loc, names in by_loc.items():
        if len(names) >= 2 and any(n in added for n in names):
            coord = ",".join(str(c) for c in loc)
            print(f"warning: {len(names)} actors share Location ({coord}): {', '.join(sorted(names))}",
                  file=sys.stderr)


def _ingest_actor_t3d(args, src, level, text, *, verb: str,
                      labels_override: frozenset[str] | None = None,
                      labels_add: frozenset[str] | None = None) -> int:
    """Shared ingest for `actor add` and `actor duplicate`: parse a T3D snippet, drop transient
    builder brushes, apply folder precedence, validate classes/textures, allocate fresh
    `<stem>_<rand>` Names, add each actor to `level` with CSG-order placement, save, and print the
    new Names to stdout (allocation order) with a count to stderr. `text` is the T3D to ingest —
    for `actor add` the --file/stdin input, for `actor duplicate` the source actors' show-blocks.
    `verb` only labels the save + summary. `labels_override` (set by the ADD handler ONLY, from
    `--label`) REPLACES each ingested actor's carrier-parsed labels, mirroring `folder_override`;
    absent (None), the `// uedctl-labels:` carrier wins. It is a PARAM — not read from `args.label`
    inside — because `duplicate` also has `--label` but needs a UNION channel, not this override.
    `labels_add` (set by the DUPLICATE handler ONLY) is that UNION channel: each ingested actor's
    labels become `resolved_labels ∪ labels_add` (used for the fresh `dup-<rand>` batch token plus
    duplicate's additive `--label`). `add` never sets `labels_add`; `duplicate` never sets
    `labels_override` — they are distinct, non-conflated channels.
    Returns the process exit code."""
    # parse_t3d_actors (NOT parse_t3d): a Name-keyed dict silently drops all-but-last of any
    # duplicate-Named group in user-concatenated T3D (14 same-Named merlons → 1). The uniquify
    # loop below then mints a distinct `<stem>_<rand>` identity per actor.
    incoming_actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]
    if not incoming_actors:
        raise _SelectionExit("no actors found in the T3D input (nothing to add)")
    # Folders are trunk-only, and a `// uedctl-folder:` carrier is a folder surface too: reject
    # `--target stash|prefab` when the input carries a folder (else StashLevelSource.save would
    # DROP it silently — the exact outcome the guard exists to prevent; the explicit-`--folder`
    # case is already caught pre-resolve). Fires only when a folder is actually present.
    if any(a.folder is not None for a in incoming_actors):
        _reject_nonlevel_target_for_folders(args)
    # Same for a `// uedctl-labels:` carrier — labels are trunk-only this slice (no stash/prefab
    # channel), so a carrier into a box would drop silently on save; reject it (the explicit
    # `--label` case is already caught pre-resolve). Fires only when a label is actually present.
    if any(a.labels for a in incoming_actors):
        _reject_nonlevel_target_for_labels(args)
    # Folder precedence (spec §4): an explicit `--folder` OVERRIDES any `// uedctl-folder:`
    # carrier the parser read into `actor.folder`; absent it, the carrier (from `actor show`)
    # stands; absent both, the actor is unfoldered. Validate every resulting folder BEFORE the
    # write loop (all-or-nothing — save is after the loop, so a raise here writes nothing).
    folder_override = getattr(args, "folder", None)
    if folder_override is not None:
        try:
            folderlib.validate_folder_path(folder_override)
        except ValueError as e:
            raise _SelectionExit(str(e))
    else:
        for a in incoming_actors:
            if a.folder is not None:                  # a carrier (possibly hand-edited) → validate
                try:
                    folderlib.validate_folder_path(a.folder)
                except ValueError as e:
                    raise _SelectionExit(f"in `// uedctl-folder:` carrier: {e}")
    # Label precedence mirrors folders: `labels_override` (explicit `--label`) REPLACES the carrier;
    # absent, the carrier stands. Validate every resulting label BEFORE the write loop.
    if labels_override is not None:
        for lbl in labels_override:
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise _SelectionExit(str(e))
    else:
        for a in incoming_actors:
            for lbl in a.labels:                      # a carrier (possibly hand-edited) → validate
                try:
                    labellib.validate_label(lbl)
                except ValueError as e:
                    raise _SelectionExit(f"in `// uedctl-labels:` carrier: {e}")
    if labels_add is not None:                        # duplicate's UNION channel: validate before write
        for lbl in labels_add:
            try:
                labellib.validate_label(lbl)
            except ValueError as e:
                raise _SelectionExit(str(e))
    # Author-time gate: qualify bare classes → FQCN + existence-validate classes & texture refs
    # (AFTER the builder-brush filter above — qualifying `Brush`→`Engine.Brush` first would let
    # the transient builder brush escape it). All-or-nothing: raises before the write loop below.
    _validate_ingest_actors(incoming_actors, args)
    # git-native: coordination-free random-suffix identity (decisions 2026-07-05 15:11) so two
    # concurrent branch-adds never collide add/add on the actor dir.
    existing = {a.name for a in level.actors.values()}
    new_names = []
    for a in incoming_actors:
        stem = a.name          # keep the name as-authored (e.g. `--base-name Pillar1` → `Pillar1_<rand>`)
        n = trunk.alloc_name(stem, existing)
        existing.add(n)
        new_names.append(n)
    touched = []
    for actor, new_name in zip(incoming_actors, new_names):
        actor.name = new_name
        if folder_override is not None:               # explicit --folder wins over any carrier
            actor.folder = folder_override
        if labels_override is not None:               # explicit --label wins over any carrier
            actor.labels = labels_override
        if labels_add is not None:                    # duplicate: union onto the resolved labels
            actor.labels = actor.labels | labels_add
        if actor.brush is not None:
            actor.brush.model_name = f"Model_{new_name}"
            actor.props = [
                ("Brush", f"Model'MyLevel.Model_{new_name}'") if k == "Brush" else (k, v)
                for k, v in actor.props
            ]
            validate_brush(actor.brush)            # reject degenerate geometry pre-store
        level.actors[new_name] = actor
        level.order = order_after_add(level.order, new_name)
        touched.append(new_name)
    _warn_duplicate_point_locations(level, touched)   # advisory: stacked point actors are silent
    # CSG-order placement (spec §2): default `last` == today's append (no override). A non-last
    # placement mints ranks in the target gap for the new block, keeping emit order. Trunk-only
    # (a stash/prefab target with a non-last `--order` was rejected pre-resolve).
    order_override: dict[str, str] | None = None
    order_spec = getattr(args, "order", "last") or "last"
    if order_spec.strip().casefold() != "last":
        selector, ref = _parse_add_order(order_spec)
        if ref is not None:
            try:
                ref = query.resolve_actor_name(level, ref)   # before=/after=NAME must exist
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            # …and be a PRE-EXISTING actor: `level` already holds the just-added block, so a ref
            # resolving to one of those (not in the load snapshot `src._ranks`) is not a valid
            # placement anchor — reject cleanly instead of a bare KeyError in `_placement_gap`.
            if ref not in src._ranks:
                raise _SelectionExit(
                    f"actor {verb} --order {selector}=NAME: {ref} is not an existing actor")
        try:                                         # src._ranks excludes the not-yet-saved new names
            order_override = order_ops.compute_add_ranks(src._ranks, new_names, selector, ref)
        except ValueError as e:                      # adjacent/duplicate imported ranks — no gap
            raise _SelectionExit(f"cannot place: {e}")
    src.save(verb=verb, args={"names": touched}, level=level, touched=touched,
             ranks=order_override)
    # Allocated Names → stdout (one/line, allocation order), ONLY AFTER the save returns so a
    # live `add - | prop -` pipe's downstream load() can never race ahead of the trunk write
    # (spec 2026-07-18 §8). The human-facing count goes to stderr — never polluting the pipe.
    for n in touched:
        print(n)
    summary = "added" if verb == "add" else "duplicated"
    print(f"{summary} {len(touched)} actor(s)", file=sys.stderr)
    return 0


def _fmt_coord_component(value) -> str:
    """A single bbox coordinate as a tidy string: an integer when integral (`512`), else the exact
    decimal (`2.5`). Decimal so no float binary tail leaks into the printed value."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    if d == d.to_integral_value():
        return str(int(d))
    # drop trailing zeros (2.500000 → 2.5); `f` keeps plain decimal form (never E-notation)
    return format(d.normalize(), "f")


def _num_coord_component(value):
    """A bbox coordinate as a JSON number: `int` when integral, else `float`. Keeps whole-number
    coords printing as `512` (not `512.0`) while still yielding valid JSON."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return int(d) if d == d.to_integral_value() else float(d)


def _bbox_of(actors):
    """Compute the world AABB enclosing `actors` as Decimal (lo, hi, size, center). Reuses
    `writes.union_bounds` → `writes.actor_bounds`, which honours the full actor transform
    (`Location + PostScale·R·MainScale·(v − PrePivot)`, the same math as `rotation.world_vertices`)
    and treats a point actor as a zero-size box at its Location."""
    lo, hi = writes.union_bounds(actors)
    lo = tuple(Decimal(str(c)) for c in lo)
    hi = tuple(Decimal(str(c)) for c in hi)
    size = tuple(hi[i] - lo[i] for i in range(3))
    center = tuple((hi[i] + lo[i]) / 2 for i in range(3))
    return lo, hi, size, center


def _rotation_prop_uu(rot_uu):
    """(pitch,yaw,roll) FRotator fields for a `--rotate PITCH,YAW,ROLL` triple given in **unreal
    rotation units** (16384 = 90°), rounded to the integer field and wrapped mod 65536."""
    return tuple(rotation.uu_field(c) for c in rot_uu)


def _offgrid_flags(verts) -> list[bool]:
    """Per-vertex: is any component off the integer grid (> CLEAN_EPS from an integer)? World-vertex
    order is stable across a rotation (rotation moves coordinates, never reorders), so a pre- and a
    post-rotation call align element-wise for a "what did the rotation newly push off-grid?" diff."""
    return [any(abs(c - round(c)) > 1e-3 for c in w) for w in verts]


def _apply_generator_org(actors, args) -> None:
    """Set the `folder`/`labels` sidecar fields on generator-emitted actors from `--folder`/`--label`
    (both validated with the same rules as `actor folder set`/`actor label add`), so `emit_actor_t3d`
    renders the `// uedctl-folder:`/`// uedctl-labels:` carriers that `actor add` reads back. Generators
    are the single place organization is authored; `actor add` no longer carries these flags. No-op for
    the flags left unset. Grammar errors surface as a CLI error naming the offending value."""
    from . import folderlib, labellib
    folder = getattr(args, "folder", None)
    labels = getattr(args, "label", None) or []
    if folder is not None:
        try:
            folderlib.validate_folder_path(folder)
        except ValueError as e:
            raise _SelectionExit(str(e))
    for lbl in labels:
        try:
            labellib.validate_label(lbl)
        except ValueError as e:
            raise _SelectionExit(str(e))
    labelset = frozenset(labels)
    for actor in actors:
        if folder is not None:
            actor.folder = folder
        if labelset:
            actor.labels = actor.labels | labelset


def _apply_generator_rotate(actors, rot_uu) -> None:
    """Feature 7: SET the emitted actors' Rotation field to the ABSOLUTE `rot_uu` — unreal rotation
    units, 16384 = 90° — a fresh generated actor is identity, so this is a plain set, not an add.
    Injects a `Rotation` prop (rotation is stored, NOT vertex-baked). No-op ONLY when `rot_uu` is
    None (the flag was not given): an EXPLICIT `--rotate 0,0,0` writes `(Pitch=0,Yaw=0,Roll=0)`,
    because omitting the property does not mean "unrotated" — it means "the CLASS DEFAULT", and
    `TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)`, so the omission would build it
    pitched 90° (2026-07-25; the same rule fixed in `actor rotate`). Warns (stderr) only when the
    rotation NEWLY carries a brush vertex off the integer grid (a shape whose own geometry is
    already fractional — e.g. a cylinder ring — is not blamed on `--rotate`)."""
    if rot_uu is None:
        return
    uu = _rotation_prop_uu(rot_uu)
    deg_str = ",".join(str(c) for c in rot_uu)
    for actor in actors:
        # off-grid vertices BEFORE the rotation — the shape's own fractional geometry, if any
        before = _offgrid_flags(rotation.world_vertices(actor)) if actor.brush is not None else []
        props = [(k, v) for k, v in actor.props if k != "Rotation"]
        idx = next((i for i, (k, _) in enumerate(props) if k == "Brush"), len(props))
        props.insert(idx, ("Rotation", f"(Pitch={uu[0]},Yaw={uu[1]},Roll={uu[2]})"))
        actor.props = props
        if actor.brush is not None:
            after = _offgrid_flags(rotation.world_vertices(actor))
            if any(a and not b for b, a in zip(before, after)):   # rotation NEWLY pushed one off-grid
                print(f"warning: --rotate {deg_str} carries some of {actor.name}'s brush vertices "
                      f"off the integer grid; the editor will snap them on import/rebuild",
                      file=sys.stderr)


# The two stderr ADVISORIES of the swept generators. Both are gated on the shape, so no existing
# verb changes behaviour: `brush build cylinder --radius 48` has inherently fractional ring
# vertices and a green test asserting it says nothing (`test_generators.py`), and a 16-step
# staircase already emits 66 faces. Whether the poly budget should also cover those shapes is an
# open question filed on `board/inbox.md` rather than decided here.
_SWEPT_SHAPES = frozenset({"extrude", "revolve"})
_POLY_BUDGET = 64


def _advise_swept_brush(shape: str, actors, *, mover_class, poly_flags: int) -> None:
    """Print the swept generators' two advisories to STDERR — stdout stays a clean T3D snippet and
    the exit status is unaffected (these report a legitimate build, not a half-answer).

    1. **Off-grid + solid.** A revolve is off the integer grid by construction (every vertex away
       from `θ=0` lands on `radius·cos/sin θ`) and uedctl deliberately preserves genuine fractions.
       An off-grid *solid* brush throws its BSP partition planes off-grid too, landing faces inside
       the engine's `SplitWithPlane`/`RemoveColinears` tolerance bands — slivers, T-junctions,
       dropped faces, holes. The prescribed mitigation is `--solidity semisolid`, which receives
       cuts but emits no world-splitting planes. Gated on non-mover as well as on solidity: a mover
       REJECTS `--solidity`, so it always lands on the solid flag value (0) while never
       partitioning the world.
    2. **Poly budget.** A 16-segment revolve of an 8-point profile is 128 swept faces plus caps —
       a lot of BSP for one brush.
    """
    if shape not in _SWEPT_SHAPES:
        return
    for actor in actors:
        if actor.brush is None:
            continue
        if (mover_class is None and poly_flags == 0
                and any(_offgrid_flags(rotation.world_vertices(actor)))):
            print(f"warning: brush build {shape}: {actor.name} has vertices off the integer grid "
                  f"AND is solid — an off-grid solid throws its BSP splitting planes off-grid too "
                  f"(slivers, T-junctions, holes in the built map). Consider --solidity semisolid "
                  f"where this is detail rather than structure, or author on-grid points",
                  file=sys.stderr)
        faces = len(actor.brush.polys)
        if faces > _POLY_BUDGET:
            caps = sum(1 for p in actor.brush.polys if p.item == "Cap")
            print(f"warning: brush build {shape}: {actor.name} has {faces} faces "
                  f"({faces - caps} swept + {caps} cap) — a heavy brush for the BSP; consider a "
                  f"simpler profile, fewer --segments, or --solidity semisolid so it does not "
                  f"partition the world", file=sys.stderr)


def _git_toplevel(path: Path) -> str | None:
    """The git working-tree root containing `path`, or None if `path` is not inside a git repo.
    Raises OSError/SubprocessError if git itself is unavailable (the caller decides what to do)."""
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _tool_repo_toplevel() -> str | None:
    """The git repo uedctl's OWN source lives in — None when installed (pipx/site-packages, not a
    repo). Used to tell a real project repo apart from a scratch project sitting INSIDE the uedctl
    source tree, which would otherwise make git walk up and report uedctl's branch."""
    try:
        return _git_toplevel(Path(__file__).resolve().parent)
    except (OSError, subprocess.SubprocessError):
        return None


_DETECT_TOOL_REPO = object()   # sentinel: "detect from uedctl's install", distinct from a real None


def _git_hint(root: Path, trunk_dir: Path, *, tool_repo_root=_DETECT_TOOL_REPO) -> str | None:
    """Best-effort one-line git state for the LEVEL's OWN project repo (not uedctl's): the branch,
    plus the count of uncommitted changes SCOPED to the level's trunk dir. Returns a "not a git
    repo" note when the project root is not tracked in its own repo — including the case where it
    only lives inside uedctl's OWN source tree (git would otherwise leak uedctl's branch/status,
    the reported bug). None only when git itself is unavailable. `tool_repo_root` is injectable for
    tests (a sentinel default means "detect from uedctl's install location").
    Read-only — uedctl never runs git operations, this only reports (decisions 2026-07-05 19:50)."""
    if tool_repo_root is _DETECT_TOOL_REPO:
        tool_repo_root = _tool_repo_toplevel()
    try:
        proj_top = _git_toplevel(root)
        if proj_top is None:
            return "project is not a git repo"
        if tool_repo_root is not None and proj_top == tool_repo_root:
            # The project isn't its own repo — it's incidentally inside uedctl's source tree.
            return "project is not a git repo (it lives inside the uedctl tool tree, not its own repo)"
        # `branch --show-current` (not `rev-parse --abbrev-ref HEAD`) so a fresh repo with no commits
        # yet — an unborn branch — still reports its branch instead of failing.
        branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                capture_output=True, text=True, timeout=5)
        if branch.returncode != 0:
            return "project is not a git repo"
        branch_name = branch.stdout.strip() or "(detached HEAD)"
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", str(trunk_dir)],
                               capture_output=True, text=True, timeout=5)
        n = len([ln for ln in dirty.stdout.splitlines() if ln.strip()])
        return f"on branch {branch_name}; {n} uncommitted change(s) in this level — see `git status`"
    except (OSError, subprocess.SubprocessError):
        return None


def _level_create(args) -> int:
    """Scaffold a NEW level: `maps/<name>/` with a single `Engine.LevelInfo` actor. Materialize
    REQUIRES a LevelInfo — a level with none inherits `MAP NEW`'s default LevelInfo, which survives
    the re-import and fails post-verify (an actor the trunk lacks). Refuses to clobber an existing
    non-empty level. `Engine.LevelInfo` is the substrate-agnostic base (DeusEx's DeusExLevelInfo
    subclasses it; the base loads in-game — verified live). To edit the new level, export it:
    `export UEDCTL_LEVEL=<name>` (there is no `--select`: a child process can't set the parent
    shell's env — decisions 2026-07-20)."""
    project = _resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    name = args.name
    # Leading dot rejected too: `maps/.locks/` is the (self-ignored) lock home — a dotted level
    # would nest inside/beside it and silently hide from git (review fix, 2026-07-18).
    if not name or "/" in name or "\\" in name or name in (".", "..") or name.startswith("."):
        print(f"invalid level name: {name!r}", file=sys.stderr)
        return 2
    level_dir = maps_dir / name
    actors_dir = level_dir / "actors"
    if actors_dir.is_dir() and any(actors_dir.iterdir()):
        print(f"level already exists: {name} (has actors at {actors_dir})", file=sys.stderr)
        return 2
    level = parse_t3d("Begin Map\nBegin Actor Class=Engine.LevelInfo Name=LevelInfo\n"
                      "    Name=\"LevelInfo\"\nEnd Actor\nEnd Map")
    level.order = list(level.actors)
    ranks = {n: trunk.append_rank({}) for n in level.actors}
    trunk.write_level(level_dir, level, ranks)
    print(f"created level: {name}")
    print(f"to edit it: export UEDCTL_LEVEL={name}", file=sys.stderr)
    return 0


def _level_list(args) -> int:
    """`level list` — enumerate the project's levels (trunk dirs under <maps>), one name per line to
    stdout (the producer convention — pipe-friendly), a count + the ambient `$UEDCTL_LEVEL` to stderr.
    `--json` emits a JSON array of {name, active} to stdout. Needs a project but NO ambient level
    (routed before the trunk-level resolution, like `project show`). The marker reads the RAW env
    (stripped, unvalidated): `level list` is exactly the command you'd run to NOTICE a bad export, so
    it must never itself error/crash on one — a malformed or stale value simply shows as `(not
    listed)`, never a `LevelSelectionError`."""
    project = _resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    levels = level_select.list_levels(maps_dir)
    active = (os.environ.get("UEDCTL_LEVEL") or "").strip() or None   # raw; never validated here
    if getattr(args, "json", False):
        import json
        print(json.dumps([{"name": n, "active": n == active} for n in levels]))
    else:
        for n in levels:
            print(n)
    # Keep the stderr note consistent with the listing/JSON: a stale/bad $UEDCTL_LEVEL (its level
    # since deleted, its actors/ tree removed, or a malformed value) is flagged as not-listed, not
    # silently reported as present — otherwise stderr would name an "active" level absent from stdout.
    if not active:
        act_note = "no level set ($UEDCTL_LEVEL unset)"
    elif active in levels:
        act_note = f"$UEDCTL_LEVEL={active}"
    else:
        act_note = f"$UEDCTL_LEVEL={active} (not listed)"
    print(f"{len(levels)} level(s); {act_note}", file=sys.stderr)
    return 0


def _level_status(args) -> int:
    import json
    project = _resolve_project(args)
    root = Path(project.root)
    target = getattr(args, "tree", None)
    want_json = getattr(args, "json", False)
    # The friendly "no level" hint (a 0-exit, not an error) applies ONLY when defaulting with NO
    # ambient level set. With an explicit --tree there's a target; with a SET-but-bad $UEDCTL_LEVEL
    # the resolve below raises the real exit-2 error (a stale export is a mistake worth surfacing).
    if target is None and not (os.environ.get("UEDCTL_LEVEL") or "").strip():
        if want_json:
            print(json.dumps({"selected": None}))   # explicit null so a script can detect "no level"
        else:
            print(level_select.NO_LEVEL_MSG)
        return 0
    # An explicit --tree (incl. "") is NOT the friendly-hint path — it resolves below, so `--tree ""`
    # errors ("must be KIND/NAME") instead of silently reading the ambient level.
    src = _resolve_level_source(args)               # honors --tree; else the ambient level (bad → exit 2)
    level = src.load()                              # populates src._ranks (trunk) / leaves it {} (box)
    total, brushes, points = _level_actor_counts(level)
    dups = trunk.duplicate_ranks(src._ranks)        # a box has no order_value sidecar → {} → no warning
    # The git hint is a level-trunk concept only (a stash/prefab box has no repo); None for a box.
    git_hint = _git_hint(root, src.trunk_dir) if isinstance(src, TrunkLevelSource) else None
    # Texture-only: class/mesh/sound packages aren't string-derivable from a T3D (referenced_packages).
    pkgs = sorted(stashlib.referenced_packages(list(level.actors.values())))
    if want_json:
        print(json.dumps({
            "kind": src.kind, "name": src.display_name,
            "actors": {"total": total, "brush": brushes, "point": points},
            "duplicate_order_values": len(dups),
            "git": git_hint,                        # the one-line hint string, or null (box / git absent)
            "texture_packages": pkgs,
        }, indent=2))
        return 0
    print(f"{src.kind}: {src.display_name}")        # e.g. "level: castle", "stash: bay", "prefab: door"
    print(f"actors: {total}  ({brushes} brush, {points} point)")
    if dups:
        print(f"WARNING: {len(dups)} order_value(s) shared by 2+ actors — arbitrary CSG order; "
              "run `level doctor`")
    if git_hint:
        print(git_hint)
    print(f"texture packages: {', '.join(pkgs) if pkgs else '(none referenced)'}")
    return 0


def _event_graph(args, src) -> int:
    """`event graph` — print the current level's Tag<->Event trigger wiring + lint. Pure,
    model-side (no editor). Default: one edge per line to stdout, lint + counts to stderr.
    `--dot`: Graphviz DOT to stdout (lint to stderr). `--json`: {nodes,edges,lint} to stdout (lint
    folded in). Exit 0 on any successful scan — a query/producer verb; lint is advisory (decision
    2026-07-18 20:54 UTC). Real errors (no project/level) still exit 2 via the standard guards."""
    from . import eventgraph
    level = src.load()
    graph = eventgraph.build_graph(level, _mover_index(args, "event graph"))
    findings = eventgraph.lint_graph(graph, level)
    if getattr(args, "json", False):
        import json
        print(json.dumps(eventgraph.to_json_obj(graph, findings), indent=2))
        return 0
    if getattr(args, "dot", False):
        print(eventgraph.format_dot(graph))
    else:
        text = eventgraph.format_text(graph)
        if text:
            print(text)
    # Human summary + lint → stderr (never pollutes the stdout wiring pipe).
    print(f"{len(graph.nodes)} eventing actor(s), {len(graph.edges)} wire(s), "
          f"{len(findings)} lint finding(s)", file=sys.stderr)
    for f in findings:
        print(f"lint[{f.kind}]: {f.message}", file=sys.stderr)
    return 0


def _project_show(args) -> int:
    """Print the resolved project root, its game, the three managed dirs (maps/prefabs/catalog),
    and the composed package search path with per-entry shadow provenance (project overlay shadows
    game base). Read-only eyeball diagnostic — the format is not a machine contract."""
    project = _resolve_project(args)                     # no project ⇒ _ProjectError → exit 2
    user_config = config.load_user_config()
    if user_config is None:                              # separate hard error — decision 2026-07-06 05:12
        raise _ProjectError(
            "no per-user games config (~/.uedctl/config.toml): needed to resolve the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    files = config.composed_search_files(project, user_config)   # missing game ⇒ ConfigError → exit 2
    if getattr(args, "json", False):
        import json
        print(json.dumps({
            "root": str(project.root),
            "game": project.game,
            "maps": str(config.project_maps_dir(project)),
            "prefabs": str(config.project_prefabs_dir(project)),
            "catalog": str(config.project_catalog_dir(project)),
            "search_path": [{"path": str(path), "provenance": provenance}
                            for path, provenance in files],
        }, indent=2))
        return 0
    print(f"root:     {project.root}")
    print(f"game:     {project.game}")
    print(f"maps:     {config.project_maps_dir(project)}")
    print(f"prefabs:  {config.project_prefabs_dir(project)}")
    print(f"catalog:  {config.project_catalog_dir(project)}")
    print(f"search path ({len(files)} package(s), project shadows base):")
    for path, provenance in files:
        print(f"  {f'[{provenance}]':<9} {path}")   # [project]/[base] tags, path column aligned
    return 0


def _composed_load_set(project) -> list[str]:
    """The whole composed-search-path load set for materialize/preview (decision 2026-07-05 23:00):
    config.composed_search_files (project overlay shadows game base) → bare package names for
    ensure_load. Hard-errors without a per-user games config (decision 2026-07-06 05:12)."""
    from .packages import search_path_package_names
    user_config = config.load_user_config()
    if user_config is None:                             # hard error — decision 2026-07-06 05:12
        raise _ProjectError(
            "no per-user games config (~/.uedctl/config.toml): materialize needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    return search_path_package_names(config.composed_search_files(project, user_config))


def _composed_dirs(project) -> list[str]:
    """The WHOLE composed config dir set (host) that becomes the editor/game/build `/resources/<n>`
    mounts for materialize/preview (one uniform set — decisions.md 2026-07-14, no content-vs-code
    split). `/stubs` is first on the crafted Paths, so a v69 stub shadows any same-named v68 `.u` a
    code dir contributes. Hard-errors without a per-user games config (decision 2026-07-06 05:12)."""
    user_config = config.load_user_config()
    if user_config is None:                             # hard error — decision 2026-07-06 05:12
        raise _ProjectError(
            "no per-user games config (~/.uedctl/config.toml): materialize needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    return config.composed_search_dirs(project, user_config)


def _level_materialize(args) -> int:
    from .apply import run_materialize
    if not args.out:                                    # check before computing the load set
        print("level materialize requires --out <path>", file=sys.stderr)
        return 2
    project = _resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    # Level-only: `--tree level/<name>` or the ambient $UEDCTL_LEVEL (a stash/prefab has no world to
    # build). Announce the level when it came from the env — materialize WRITES a map, so a stale
    # export would silently build the wrong level (decisions 2026-07-20).
    name, from_env = _resolve_level_only(args, verb="materialize")
    if from_env:
        _announce_env_level(name, action="materializing")
    src = TrunkLevelSource(maps_dir / name)
    level = src.load()
    dups = trunk.duplicate_ranks(src._ranks)
    if dups:
        print(f"WARNING: {len(dups)} order_value(s) shared by 2+ actors — arbitrary CSG order; "
              "run `level doctor`", file=sys.stderr)
    result = run_materialize(level=level, packages=_composed_load_set(project),
                             search_dirs=_composed_dirs(project),
                             schema_resolver=_schema_resolver_for(project),
                             out_path=args.out, overwrite=args.overwrite,
                             state_dir=config.state_dir(project.root, create=True),
                             no_verify=getattr(args, "no_verify", False),
                             keep_build=getattr(args, "keep_build", False))
    if result.rc != 0:
        print(result.message, file=sys.stderr)
        return result.rc
    print(result.message)
    return 0


def _level_preview(args) -> int:
    """`level preview` — freely-posed still shots of the current level. The DEFAULT backend
    is `--game` (the faithful tier, spec 2026-07-13): it delivers the map into a WARM per-user
    headless-game container and captures truly-lit first-person frames (real lighting/sky/
    meshes). `--native` is the opt-in offline DRAFT tier (spec 2026-07-16): the Rust CSG core
    carves the trunk in-process and software-rasterizes flat-shaded stills — fast, no editor/
    container/game, but no lighting/meshes/sky. `use_game = not args.native` picks the tier
    (the two flags are mutually exclusive; neither given ⇒ game). All SHOT tokens validate up
    front, all-or-nothing, before any work."""
    from .preview_native import DEFAULT_FOV, NativePreviewError, render_shots
    from .preview_shots import parse_shot

    use_game = not args.native          # --game is the DEFAULT tier; --native is the opt-in draft

    if use_game and args.fov is not None:
        print("--fov requires --native (the in-game tier renders at the game's own FOV)",
              file=sys.stderr)
        return 2
    if not use_game:
        for value, flag in ((args.map, "--map"), (args.rebuild, "--rebuild"),
                            (args.keep_alive, "--keep-alive")):
            if value:
                print(f"{flag} requires --game (the in-game preview tier)", file=sys.stderr)
                return 2
    # `--tree` selects a TRUNK level; `--map` renders a retail map file — the two are mutually
    # exclusive (a --map preview never resolves a trunk level, so a --tree would be silently ignored).
    if getattr(args, "tree", None) and args.map:
        print("--tree names a trunk level; it cannot be combined with --map (a retail map file)",
              file=sys.stderr)
        return 2
    m = re.fullmatch(r"(\d+)x(\d+)", args.size.strip())
    if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
        print(f"invalid --size {args.size!r}: expected WxH in pixels, e.g. 1280x960",
              file=sys.stderr)
        return 2
    size = (int(m.group(1)), int(m.group(2)))
    list_cls = getattr(args, "list_actors", None)
    if list_cls:
        if not use_game or not args.map:
            print("--list-actors is a --game --map query (it inspects a retail map's actors)",
                  file=sys.stderr)
            return 2
        if args.shots:
            print("--list-actors is a query — drop the SHOT tokens", file=sys.stderr)
            return 2
    else:
        if not args.out_dir:
            print("--out-dir is required (unless --list-actors)", file=sys.stderr)
            return 2
        if not args.shots:
            print("need at least one SHOT token (or use --list-actors to discover @Actor refs)",
                  file=sys.stderr)
            return 2
    if getattr(args, "sample", 0):
        if not list_cls:
            print("--sample only applies with --list-actors", file=sys.stderr)
            return 2
        if args.sample < 0:
            print(f"--sample must be >= 0, got {args.sample}", file=sys.stderr)
            return 2
    try:
        shots = [parse_shot(t) for t in args.shots]         # all-or-nothing (exit 2)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    project = _resolve_project(args)
    user_config = config.load_user_config()
    if user_config is None:                                 # same hard error as materialize
        print("no per-user games config (~/.uedctl/config.toml): preview resolves packages "
              "over the game's base paths; create it with a [games.<name>] paths dir list",
              file=sys.stderr)
        return 2

    if use_game:
        from .preview_game import GamePreviewError
        from . import preview_game
        if list_cls:                            # QUERY mode: print the map's actors, no screenshots
            try:
                out = preview_game.list_actors(
                    project=project, user_config=user_config, game=project.game,
                    map_path=args.map, cls=list_cls, sample=getattr(args, "sample", 0))
            except GamePreviewError as e:
                print(str(e), file=sys.stderr)
                return 2
            sys.stdout.write(out)
            return 0
        level = name = None
        if args.map is None:                    # trunk mode needs a level (--map renders a retail map)
            maps_dir = Path(config.project_maps_dir(project))
            name, _ = _resolve_level_only(       # level-only; preview is a READ → no echo
                args, verb="preview",
                alt_hint="use `stash preview` / `prefab preview` to render a captured set")
            level = TrunkLevelSource(maps_dir / name).load()
        try:
            n = preview_game.render_shots(
                shots=shots, out_dir=Path(args.out_dir), size=size, project=project,
                user_config=user_config, game=project.game, level=level, level_name=name,
                map_path=args.map, rebuild=args.rebuild, keep_alive=args.keep_alive)
        except GamePreviewError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"wrote {n} shot(s) to {args.out_dir}")
        return 0

    maps_dir = Path(config.project_maps_dir(project))
    name, _ = _resolve_level_only(               # native draft is always trunk mode; READ → no echo
        args, verb="preview",
        alt_hint="use `stash preview` / `prefab preview` to render a captured set")
    src = TrunkLevelSource(maps_dir / name)
    level = src.load()
    search_files = config.composed_search_files(project, user_config)
    try:
        n = render_shots(level=level, shots=shots, out_dir=Path(args.out_dir), size=size,
                         fov=args.fov if args.fov is not None else DEFAULT_FOV,
                         search_files=search_files,
                         index=_mover_index(args, "level preview --native", project=project))
    except NativePreviewError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"wrote {n} shot(s) to {args.out_dir}")
    return 0


def _level_doctor(args, src) -> int:
    """Static, offline BSP/geometry lint (no editor). Exit code reflects ALL findings (a
    suppressed-from-display ERROR still fails); --severity/--category filter DISPLAY only. Reads the
    box via the LevelSource seam — $UEDCTL_LEVEL by default, or a `--tree level|stash|prefab`
    box (a stash/prefab has no order_value sidecar, so `_ranks` is empty → no duplicate-order finding,
    which is correct: a box doesn't carry CSG precedence)."""
    import json
    from . import doctor

    level = src.load()
    level_name = src.display_name
    findings = doctor.sort_findings(
        doctor.run_doctor(level, _mover_index(args, "level doctor"))
        + doctor.check_duplicate_order(src._ranks))
    exit_severity = doctor.worst(findings)        # over ALL findings, before display filtering

    if args.category:
        wanted = {c.strip() for c in args.category.split(",")}
        if unknown := (wanted - set(doctor.CATEGORIES)):
            print(f"unknown --category: {', '.join(sorted(unknown))}; valid: "
                  f"{', '.join(doctor.CATEGORIES)}", file=sys.stderr)
            return 2
        shown = [f for f in findings if f.category in wanted]
    else:
        shown = findings
    if args.severity:
        floor = doctor._RANK[doctor.Severity(args.severity)]
        shown = [f for f in shown if doctor._RANK[f.severity] >= floor]

    if args.json:
        print(json.dumps([{**f.__dict__, "severity": f.severity.value} for f in shown], indent=2))
    else:
        print(doctor.format_report(shown, level_name))
    return 1 if exit_severity is doctor.Severity.ERROR else 0


# ── actor prop: the grammar/planner/effective-value logic lives in `propedit.py` (spec
# 2026-07-18); dispatch wires the handlers + the four mockable schema seams below. ──────────


def _class_schema(cls: str, project=None) -> dict:
    """{casefold(name): Prop} for `cls`, extracted offline from the real game `.u` (P1). Raises
    `uprops.SchemaError` on an unbuildable/unknown schema — no fallback (decision 2026-06-26 14:10).
    The schema SEAM: tests patch this to run offline without the gitignored v68 install.

    The schema code path is the config-driven code dirs (decisions.md 2026-07-14 03:30 — same
    source stubs come from). `project` is the invocation's RESOLVED project, threaded from the
    `actor prop` handler so a `--project <dir>` override reaches the schema path (asset-wiring Part
    B); if omitted it is re-resolved from cwd/env (any direct/legacy caller). A `None` project or
    absent games config → an empty code path → a clean `SchemaError` miss. A PRESENT-but-broken
    config (malformed TOML, ambiguous project, or a game named by the project but missing from the
    games config) raises `config.ConfigError` here, which `dispatch()` catches → exit 2 (never a
    traceback either way)."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCTL_PROJECT"),
                                         cwd=os.getcwd())
    user_config = config.load_user_config()
    resolver = packages.schema_resolver(project, user_config)
    return {p.name.casefold(): p for p in uprops.resolve_class_properties(cls, resolver=resolver)}


def _schema_resolver_for(project):
    """The schema-path resolver for `project` (None → cwd/env re-resolution), shared by the
    defaults/struct-member/enum seams below."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCTL_PROJECT"),
                                         cwd=os.getcwd())
    return packages.schema_resolver(project, config.load_user_config())


def _class_defaults(cls: str, project=None) -> dict:
    """{(casefold(prop), array_index): canonical text} — the class's EFFECTIVE defaults, every
    ancestor's defaults block overlaid root→leaf, decoded offline from the game's own `.u`
    (uprops.resolve_class_defaults; spec §5.2). The second MOCKABLE seam beside `_class_schema`
    — tests patch it to run offline. Raises `uprops.SchemaError` when unbuildable (no
    fallback)."""
    return uprops.resolve_class_defaults(cls, resolver=_schema_resolver_for(project))


def _struct_members(prop, project=None) -> list:
    """A StructProperty's ORDERED member Props (uprops.struct_members via the declaring
    package) — powers dot-path member validation + struct rendering. Mockable seam."""
    resolver = _schema_resolver_for(project)
    pkgs: dict = {}
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                          f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    tp, ti = uprops.resolve_type_export(dp, prop.type_ref, "Struct",
                                         resolver=resolver, _pkgs=pkgs)
    return uprops.struct_members(tp, ti, owner=prop.type_name or prop.name)


def _enum_names(prop, project=None) -> tuple:
    """A ByteProperty's enum value names, cross-package (spec §4). Mockable seam."""
    resolver = _schema_resolver_for(project)
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                          f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    return uprops.resolve_enum_names(prop, dp, resolver=resolver)


def _class_ctx(cls: str, args) -> "propedit.ClassCtx":
    """The lazy per-class schema bundle the prop verbs consume: every load routes through the
    mockable seams (`_class_schema`/`_class_defaults`/`_struct_members`/`_enum_names`), and the
    project resolves lazily + tolerantly (a no-project context is a clean SchemaError miss on
    first schema-needing token, never an early exit — spec §2.4)."""
    def proj():
        try:
            return _resolve_project(args)
        except _ProjectError:
            return None
    return propedit.ClassCtx(
        cls=cls,
        load_schema=lambda: _class_schema(cls, proj()),
        load_defaults=lambda: _class_defaults(cls, proj()),
        load_members=lambda p: _struct_members(p, proj()),
        load_enums=lambda p: _enum_names(p, proj()),
    )


def _class_index(project=None) -> "classindex.ClassIndex":
    """Build the offline `ClassIndex` for the resolved project's composed `.u` path. The MOCKABLE
    seam (tests patch it to run offline without the gitignored v68 install), mirroring
    `_class_schema`. A None project is re-resolved from cwd/env (tolerant of a no-project context —
    the caller turns an empty index into a clean 'no package path' error)."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCTL_PROJECT"),
                                         cwd=os.getcwd())
    user_config = config.load_user_config()
    if user_config is None:                 # absent games config → clean exit 2, never AttributeError
        raise _SelectionExit(_NO_GAMES_CONFIG)
    return classindex.ClassIndex.from_project(project, user_config)


def _mover_index(args, verb: str, project=None) -> "classindex.ClassIndex":
    """The class resolver the schema-aware mover gate needs. `movers.is_mover` decides mover-ness by
    walking the class hierarchy to `Engine.Mover` (decisions.md 2026-07-25 10:18 UTC), so EVERY verb
    that asks "is this actor a Mover?" — `mover key`, `level doctor`, `event graph`, `brush
    scale`/`apply-transform`/`intersect`/`deintersect`, `stash capture`, the native preview/build —
    now needs the game's `.u` packages, hence a project and the per-user games config. A missing
    games config is a clean exit 2 naming the verb and the requirement (a missing PROJECT surfaces
    as the standard `_ProjectError`); never a traceback, and never a report that silently calls
    every mover a static brush. `project` skips re-resolution where the caller already has one."""
    try:
        index = _class_index(project if project is not None else _resolve_project(args))
    except _SelectionExit as e:                      # no per-user games config
        raise _SelectionExit(f"{verb}: {e.message}; {_MOVER_RESOLVER_WHY}") from None
    if index.empty:                                  # config present, but it resolves no packages
        raise _SelectionExit(f"{verb}: {_NO_PACKAGE_PATH}; {_MOVER_RESOLVER_WHY}")
    return index


# The one explanation appended to both of `_mover_index`'s failure messages (a review fix: the
# "exits 2 naming the verb" promise held on only one of the two routes).
_MOVER_RESOLVER_WHY = ("a class resolver is required because mover detection resolves the actor's "
                       "class against Engine.Mover")

# One canonical message for "the resolved project has no game packages on its path" — used by every
# author-time validation site so the wording never diverges (a review fix).
_NO_PACKAGE_PATH = ("no package search path: this project resolves no game packages (check the games "
                    "config `paths` and that the project targets a game)")

# One canonical message for "no per-user games config" on the author-time validation paths (the
# materialize/texture/stub verbs carry their own verb-specific variants). A review fix: an absent
# `~/.uedctl/config.toml` must exit 2 cleanly here, never reach `composed_search_files` as None.
_NO_GAMES_CONFIG = ("no per-user games config (~/.uedctl/config.toml): needed to resolve the game's "
                    "base package paths; create it with a [games.<name>] paths dir list")


def _find_class_filter(args, level) -> list[str] | None:
    """The class-name filter for `actor find`, combining the two class flags (decision 2026-07-19):
    the `--exact-class` bases (exact class match, as the old `--class` did), UNIONed with every class
    present in `level` that DESCENDS from a `--subclass-of` base (descendant-aware, expanded via the
    offline `ClassIndex` — `--subclass-of Engine.Light` also matches Spotlight). The two flags OR
    within the class dimension; `list_actors` ANDs the result with the other filters.

    Returns None when NEITHER class flag was given (no class filter → every class); a possibly-empty
    list when a class flag WAS given (an empty list matches no actor — the requested filter simply
    hit nothing). Only `--subclass-of` touches the schema/project; a plain or `--exact-class`-only
    find never does. Raises `_SelectionExit` on an unknown `--subclass-of` base or a missing
    package path."""
    exact = list(getattr(args, "cls", None) or [])
    bases = list(getattr(args, "subclass_of", None) or [])
    if not exact and not bases:
        return None                                       # no class filter → match every class
    if not bases:
        return exact                                      # --exact-class only: identical to the old --class
    index = _class_index(_resolve_project(args))
    if index.empty:                                       # `empty` is a property, not a method
        raise _SelectionExit("--subclass-of needs the game's .u packages, but none were found on "
                             "the project's package path")
    qbases: list[str] = []
    for b in bases:
        try:
            fq = b if "." in b else index._qualify_bare(b)
        except ClassRefError as e:
            raise _SelectionExit(f"--subclass-of: {e}")
        if fq is None or not index.class_exists(fq):
            raise _SelectionExit(f"--subclass-of: unknown class {b!r}")
        qbases.append(fq)
    matched = set(exact)
    for cls in {a.cls for a in level.actors.values()}:    # only the classes actually present, deduped
        try:
            fq_cls = cls if "." in cls else index._qualify_bare(cls)
        except ClassRefError:
            fq_cls = None                                 # an unknown stored class can't be a descendant
        if fq_cls and any(index.descends_from(fq_cls, qb) for qb in qbases):
            matched.add(cls)                              # add the class AS STORED (list_actors matches it)
    return sorted(matched)

# `class show` (without --all) shows the class's own props + as many ancestor sections as fit in this
# many lines, then notes the rest — a deep chain (…→Engine.Actor→Core.Object) is ~200 props otherwise.
_SHOW_LINE_BUDGET = 60


def _package_path_or_exit(args):
    """Resolve the project (exit 2 if none) and return `(project, user_config, composed_files)`,
    raising one canonical `_SelectionExit` if the composed package path is empty. The single seam all
    author-time validation goes through, so the empty-path wording is identical everywhere."""
    project = _resolve_project(args)                    # exit 2 (clean) if not in a project
    user_config = config.load_user_config()
    if user_config is None:                 # absent games config → clean exit 2, never AttributeError
        raise _SelectionExit(_NO_GAMES_CONFIG)
    files = config.composed_search_files(project, user_config)
    if not files:
        raise _SelectionExit(_NO_PACKAGE_PATH)
    return project, user_config, files


def _validate_ingest_actors(actors, args) -> None:
    """The DRY author-time ingest gate: qualify bare class names → FQCN and existence-validate
    qualified ones (in place), then validate every brush poly's texture ref EXISTS on the package
    path. Shared by every T3D ingest/emit seam (actor add, stash capture/apply/promote, prefab
    apply, the generators). Raises `_SelectionExit` (exit 2) on an unknown class/texture or an empty
    package path — never a traceback. Call AFTER builder-brush filtering (qualifying `Brush`→
    `Engine.Brush` before the filter would let the transient builder brush escape it)."""
    if not actors:
        return
    project, user_config, files = _package_path_or_exit(args)
    try:
        classindex.ClassIndex.from_project(project, user_config).qualify_and_validate(actors)
    except ClassRefError as e:
        raise _SelectionExit(str(e))
    from . import utexture
    resolver = utexture.TextureResolver(files)
    for a in actors:
        if a.brush is None:
            continue
        for p in a.brush.polys:
            if p.texture is not None and not resolver.exists(p.texture):
                raise _SelectionExit(f"texture not found: {p.texture} — no Texture of that name on "
                                     f"the package path (author-time validation)")


def _validate_texture_ref(ref: str, args) -> None:
    """Existence-validate a single texture ref (for `brush poly set --texture` / `brush build
    --texture`), exit 2 (clean) if it names no Texture on the path or the path is empty."""
    if ref is None:
        return
    _project, _user_config, files = _package_path_or_exit(args)
    from . import utexture
    if not utexture.TextureResolver(files).exists(ref):
        raise _SelectionExit(f"texture not found: {ref} — no Texture of that name on the package "
                             f"path (author-time validation)")


_TREE_LINE_BUDGET = 60


def _class_tree(idx, *, subclass_of, include_non_actor, depth, package) -> list[str]:
    """The `class list` TREE (default rendering): the inheritance hierarchy under a root, indented,
    every class shown with abstract branch-points marked `*` and a frontier node's hidden direct
    subclasses shown inline as `(N)` (decision 2026-07-18). Root = `--subclass-of`, else `Core.Object`
    with `--include-non-actor`, else `Engine.Actor`. `--depth N` sets the depth (`--depth all` =
    `math.inf` = the whole tree, no `(N)` collapse); without it, the depth auto-grows while it fits the
    ~60-line budget (min 1 level). `--package P` prunes to P's classes + the ancestor branches needed to
    reach them. Direct subclasses at each level are listed in the name-sorted order `idx.subclasses()`
    returns (see `ClassIndex.children_map`)."""
    root = subclass_of or (classindex.CORE_OBJECT if include_non_actor else classindex.ENGINE_ACTOR)
    if not idx.class_exists(root):
        raise ClassRefError(f"unknown --subclass-of class: {root}" if subclass_of
                            else f"root class {root} not on the package path")
    package_cf = package.casefold() if package else None
    if package_cf is not None and package_cf not in idx._paths:
        raise ClassRefError(f"package not found on the path: {package}")

    pcache: dict[str, bool] = {}
    def has_pkg(fqcn):                               # keep a node iff it (or a descendant) is in P
        if package_cf is None:
            return True
        k = fqcn.casefold()
        if k not in pcache:
            pcache[k] = False                        # provisional: a re-entrant hit (pathological
            pcache[k] = (fqcn.split(".", 1)[0].casefold() == package_cf   # inheritance cycle) reads
                         or any(has_pkg(c) for c in idx.subclasses(fqcn)))  # as "not in P", so a
        return pcache[k]                             # cycle can't keep an out-of-package subtree in

    def kids(fqcn):
        return [c for c in idx.subclasses(fqcn) if has_pkg(c)]

    def render(maxd):
        out: list[str] = []
        def walk(fqcn, d, indent, seen):
            mark = " *" if idx.is_abstract(fqcn) else ""
            ks = kids(fqcn)
            if (d >= maxd or fqcn.casefold() in seen) and ks:
                out.append(f"{indent}{fqcn}{mark} ({len(ks)})")
            else:
                out.append(f"{indent}{fqcn}{mark}")
                for c in ks:
                    walk(c, d + 1, indent + "  ", seen | {fqcn.casefold()})
        walk(root, 0, "", frozenset())
        return out

    if depth is not None:
        eff = max(0, depth)
    else:
        eff = 1
        cur = render(eff)
        while eff < 30:
            nxt = render(eff + 1)
            if len(nxt) > _TREE_LINE_BUDGET or nxt == cur:   # over budget, or growth converged
                break
            eff, cur = eff + 1, nxt
        return cur
    return render(eff)


def _dispatch_class(args) -> int:
    """`class list` / `class show` — offline class discovery over the composed `.u` path (no editor,
    no level). Builds the `ClassIndex` from the resolved project."""
    project = _resolve_project(args)
    idx = _class_index(project)
    if idx.empty:
        raise _SelectionExit(_NO_PACKAGE_PATH)
    if args.sub == "list":
        if getattr(args, "legacy_all", False):       # `--all` was split (2026-07-18): targeted pointer
            raise _SelectionExit(
                "class list: --all was split — use --include-non-actor (non-Actor classes), "
                "--include-abstract (abstract/non-placeable), and/or --depth all (full depth).")
        subclass_of = getattr(args, "subclass_of", None)
        flat = getattr(args, "flat", False)
        include_non_actor = getattr(args, "include_non_actor", False)
        include_abstract = getattr(args, "include_abstract", False)
        depth = getattr(args, "depth", None)
        # `--include-abstract` only acts in the --flat drill/--package list; REJECT it where it can do
        # nothing (the tree, the bare category view, or ANY --depth browse — already unfiltered) rather
        # than silently no-op'ing (Andrzej 2026-07-24: error, not warn).
        if include_abstract and not (flat and depth is None
                                     and (subclass_of is not None or args.package is not None)):
            raise _SelectionExit(
                "--include-abstract is not valid here — it applies ONLY to the --flat --subclass-of "
                "drill and the --package flat list. The tree, the bare category view, and any --depth "
                "browse already show abstract classes (branch-points marked *). Drop the flag, or pair "
                "--flat with --subclass-of/--package.")
        try:
            if flat:                                 # --flat: the pipeable one-per-line list
                for fqcn in idx.list_classes(package=args.package, subclass_of=subclass_of,
                                             include_non_actor=include_non_actor,
                                             include_abstract=include_abstract, depth=depth):
                    print(fqcn)
            else:                                    # DEFAULT: the indented inheritance tree
                lines = _class_tree(idx, subclass_of=subclass_of,
                                    include_non_actor=include_non_actor,
                                    depth=depth, package=args.package)
                for line in lines:
                    print(line)
                if args.package and len(lines) == 1:     # only the root survived the --package prune
                    root_name = lines[0].strip().removesuffix(" *")   # drop the abstract mark if present
                    print(f"(no classes under {root_name} are in package {args.package})",
                          file=sys.stderr)
        except ClassRefError as e:
            raise _SelectionExit(str(e))
        return 0
    if args.sub == "show":
        if getattr(args, "legacy_all", False):       # `--all` renamed to `--depth all` (2026-07-18)
            raise _SelectionExit("class show: --all was renamed — use --depth all (the whole super chain).")
        fqcn = args.fqcn
        if not idx.class_exists(fqcn):
            raise _SelectionExit(f"unknown class: {fqcn} (package not on the path, or the package "
                                 f"does not define that class)")
        chain = idx.ancestry(fqcn)
        abstract = idx.is_abstract(fqcn)
        abs_word = {True: "abstract", False: "concrete", None: "abstract=unknown"}[abstract]
        placeable = "placeable" if idx.is_placeable(fqcn) else "not-placeable"

        def _emit(props):
            for p in props:
                dim = f"[{p.array_dim}]" if p.array_dim > 1 else ""
                enum = f" {{{', '.join(p.enum_value_names)}}}" if p.enum_value_names else ""
                print(f"  {p.name}{dim}: {p.kind}{enum}")

        # Props grouped by editor CATEGORY (UnrealEd's own property-browser view). Only EDITABLE props
        # are shown — a `var(Group)`/`var()` prop carries a category, a plain non-editable `var` has
        # category None and is HIDDEN (internal class working). `var()` (no explicit group) stores the
        # declaring class name as its category (per-class section); explicit `var(Group)` categories
        # (Movement/Display/…) cross classes. (RE'd 2026-07-18 — see unrealed/class-schema.md.)
        depth = getattr(args, "depth", None)         # int, math.inf (--depth all), or None
        categories = getattr(args, "categories", None) or []
        # The super chain (idx.ancestry, above) and the property walk BOTH resolve from the persistent
        # per-package SCHEMA CACHE (stat-tuple-keyed, version-consistent): ancestry reads super refs via
        # idx._schema, and resolve_class_properties (no `_cache` seed) takes its cache-ON path for the
        # props. Reading both from that one cache keeps the `super:` line and the prop set consistent
        # per package, which SUBSUMES the old seed (which pre-loaded each chain package as a full
        # `Package` to force one shared byte-read but thereby bypassed the warm schema cache — dropped
        # 2026-07-20 so `class show` gets the ~2.4× warm win).
        # A missing/unparseable ANCESTOR package makes the resolver return None → SchemaError, and that
        # is a HARD ERROR: exit 2 naming the package that failed. There is NO own-only degrade — printing
        # the class's own props with a stderr note is a silent half-answer (the note scrolls away and the
        # caller reads a truncated property set as a complete one). Per `direction.md` "No silent
        # half-answers" / decisions.md 2026-07-24 21:58 UTC.
        try:
            allp = uprops.resolve_class_properties(fqcn, resolver=idx.resolver())
        except uprops.SchemaError as e:
            raise _SelectionExit(f"cannot read schema for {fqcn}: {e}")
        editable = [p for p in allp if p.category is not None]

        # `--category` (repeatable, exact, case-insensitive, OR-combined) narrows the output to the
        # named editor categories AND forces the EXPANDED render at unlimited depth (spec 2026-07-18:
        # if you asked for a category you want to SEE its props, not a count — and a derived class's
        # category is often entirely inherited). `wanted` is a casefolded set, or None when unfiltered.
        wanted = None
        if categories:
            available = sorted({p.category for p in editable})
            if not available:
                raise _SelectionExit(f"class {fqcn} has no editable categories")
            avail_cf = {c.casefold() for c in available}
            for v in categories:                         # first value matching nothing is named (all-or-
                if v.casefold() not in avail_cf:         # nothing, like multi --set in actor prop)
                    raise _SelectionExit(f"no category {v!r} on {fqcn}; available: "
                                         f"{', '.join(available)}")
            wanted = {v.casefold() for v in categories}

        # Header prints only AFTER --category validation, so a rejected filter leaves stdout empty
        # (a script redirecting stdout gets nothing on an unknown-category error).
        print(f"{fqcn}  [{abs_word}, {placeable}]")
        if len(chain) > 1:
            print(f"  super: {' -> '.join(chain[1:])}")

        if depth is not None or wanted is not None:
            # EXPANDED view: own + INHERITED props per category, inherited tagged `← SourceClass`
            # (Style C). `--depth N` includes inherited from up to N superclass hops (own = hop 0);
            # `--depth all` (math.inf) / `--category` expand the WHOLE chain (unlimited depth).
            chain_cf = [c.casefold() for c in chain]     # chain[0] == this class (hop 0)

            def hop(p):                                  # superclass distance of a prop's declarer
                cf = p.owner.casefold()
                return chain_cf.index(cf) if cf in chain_cf else len(chain_cf)

            # When `--category` filters, the depth budget + omitted-levels trailer reckon over the
            # WANTED categories only, so a level holding no wanted-category prop is never counted.
            in_scope = (lambda p: True) if wanted is None else (lambda p: p.category.casefold() in wanted)
            max_hop = max((hop(p) for p in editable if in_scope(p)), default=0)

            def render(eff):                             # -> the output lines for depth `eff`
                by: dict[str, list] = {}
                for p in editable:
                    if hop(p) <= eff and in_scope(p):
                        by.setdefault(p.category, []).append(p)
                out = []
                for cat, group in by.items():
                    out.append(f"\n{cat}:")
                    for p in sorted(group, key=hop):     # own (hop 0) first; stable within a hop
                        dim = f"[{p.array_dim}]" if p.array_dim > 1 else ""
                        enum = f" {{{', '.join(p.enum_value_names)}}}" if p.enum_value_names else ""
                        # own props (hop 0) are untagged; every inherited prop is tagged with its
                        # FULLY-QUALIFIED source class.
                        tag = "" if hop(p) == 0 else f"   ← {p.owner}"
                        out.append(f"  {p.name}{dim}: {p.kind}{enum}{tag}")
                return out

            if depth is not None:
                eff = max(0, min(depth, max_hop))        # --depth N clips; --depth all (inf) → max_hop
            else:                                        # --category means the WHOLE chain (unlimited
                eff = max_hop                            # depth — a single category is narrow)
            for ln in render(eff):
                print(ln)
            if eff < max_hop:
                scope = "for the whole chain" if wanted is None else "to see every matched superclass level"
                print(f"\n(+{max_hop - eff} more superclass level(s) omitted — --depth all "
                      f"{scope})")
            return 0

        # DEFAULT: this class's OWN props grouped by category; inherited props of that category are
        # COLLAPSED to a `(+N inherited, from M superclasses)` count; categories that are ENTIRELY
        # inherited fold into one collapsed tail line (decision 2026-07-18: own-only + inherited counts).
        own_cf = fqcn.casefold()
        own_by_cat: dict[str, list] = {}
        inh_by_cat: dict[str, list] = {}                 # category -> [count, {owner classes}]
        for p in editable:
            if p.owner.casefold() == own_cf:
                own_by_cat.setdefault(p.category, []).append(p)
            else:
                d = inh_by_cat.setdefault(p.category, [0, set()])
                d[0] += 1
                d[1].add(p.owner)

        def _inh_note(n, owners):
            return f"  (+{n} inherited, from {len(owners)} superclass{'es' if len(owners) != 1 else ''})"

        lines_used = 2                                   # header (class + super)
        hidden_own: list[str] = []
        own_cats = list(own_by_cat)
        for i, cat in enumerate(own_cats):
            group = own_by_cat[cat]
            section_lines = len(group) + 2 + (1 if cat in inh_by_cat else 0)
            if i > 0 and lines_used + section_lines > _SHOW_LINE_BUDGET:
                hidden_own = own_cats[i:]
                break
            print(f"\n{cat}:")
            _emit(group)
            if cat in inh_by_cat:
                print(_inh_note(*inh_by_cat[cat]))
            lines_used += section_lines
        if hidden_own:
            noun = "category" if len(hidden_own) == 1 else "categories"
            # list the NAMES (short) so `class show <C>` is a complete category listing — `--category X`
            # is then discoverable without --depth all or a deliberate typo (spec 2026-07-18 discoverability).
            print(f"\n(+{len(hidden_own)} more own {noun} hidden: {', '.join(hidden_own)} "
                  f"— use --depth all or --category NAME)")
        only_inh = sorted(c for c in inh_by_cat if c not in own_by_cat)
        if only_inh:
            tot = sum(inh_by_cat[c][0] for c in only_inh)
            noun = "category" if len(only_inh) == 1 else "categories"
            print(f"\n(+{tot} inherited, in {len(only_inh)} more {noun}: {', '.join(only_inh)})")
        return 0
    raise _SelectionExit(f"unimplemented class sub-verb: {args.sub}")


def _dispatch_cache(args) -> int:
    """`uedctl cache clear|gc` over the per-user package-schema cache (`~/.uedctl/cache/schema`).

    - `clear` DELETES the whole cache. Pure derivable throwaway; a no-op (still exit 0) when the dir
      is already absent.
    - `gc` SHRINKS it: `schema_cache.sweep()` reclaims the orphaned `v<older>/` decoder-version dirs a
      `SCHEMA_CACHE_VERSION` bump left unreachable, then LRU-evicts current-version blobs (by atime)
      until the cache is under the byte/count cap. `--max-bytes`/`--max-entries` override the
      built-in/env defaults for this run only. Eviction has no correctness pressure — blobs are
      immutable and derivable, so an evicted one just re-decodes on next use — and `sweep()` never
      raises, so `gc` cannot fail on a racing writer or an unremovable file. The same sweep already
      runs best-effort after a cache write; this is the on-demand surface.

    Neither needs a project or an editor."""
    if args.sub == "clear":
        removed = schema_cache.clear()
        print(f"cleared {config.schema_cache_root()}" if removed
              else f"nothing to clear ({config.schema_cache_root()} does not exist)")
        return 0
    if args.sub == "gc":
        for flag, val in (("--max-bytes", args.max_bytes), ("--max-entries", args.max_entries)):
            if val is not None and val < 0:               # a negative cap is meaningless, not "unbounded"
                raise _SelectionExit(f"cache gc {flag}: must be >= 0, got {val}")
        # `-1` is sweep()'s "use the env-or-constant default" sentinel; an explicit flag overrides it.
        stats = schema_cache.sweep(
            max_bytes=-1 if args.max_bytes is None else args.max_bytes,
            max_entries=-1 if args.max_entries is None else args.max_entries)
        print(f"{config.schema_cache_root()}: removed {stats['removed_version_dirs']} old version "
              f"dir(s), evicted {stats['evicted']} entries ({stats['freed_bytes']} bytes freed); "
              f"kept {stats['kept_entries']} entries ({stats['kept_bytes']} bytes)")
        return 0
    raise _SelectionExit(f"unimplemented cache sub-verb: {args.sub}")


def dispatch(args) -> int:
    try:
        return _dispatch(args)
    except _SelectionExit as e:
        print(e.message, file=sys.stderr)
        return 2
    except (_ProjectError, level_select.LevelSelectionError, config.ConfigError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except CoordinateError as e:
        # A coordinate that cannot be written as T3D at all (non-finite, or past emit.MAX_COORD).
        # Raised from the single write path, so it covers every generator and every mutating verb
        # rather than one flag on one shape.
        print(f"invalid coordinate: {e}", file=sys.stderr)
        return 2
    except GeometryError as e:
        # Degenerate/invalid brush geometry from a model-side verb (actor add, brush clip/vertex,
        # mover key, the brush builders, stash/prefab apply) — the message carries a precise per-poly
        # diagnostic; surface it, never a traceback. (`level materialize` catches its own build-time
        # GeometryError locally with a "materialize failed" message.)
        print(f"invalid brush geometry: {e}", file=sys.stderr)
        return 2
    except (EditorBusyError, DriverError, TimeoutError) as e:
        # Any editor-driving verb (level materialize/preview) whose
        # ephemeral editor is busy, wedged, or crashes mid-drive → clean error, never a traceback.
        print(f"editor error: {e}", file=sys.stderr)
        return 2
    except ClassRefError as e:
        # An unknown/ambiguous class ref reached the top level (a `class` verb or an ingest gate that
        # didn't translate it locally) → clean exit 2, never a traceback.
        print(str(e), file=sys.stderr)
        return 2
    except SchemaError as e:
        # A `.u` layout desync (a corrupt package on the path) surfacing from a class/schema read —
        # the corrupt-package backstop so it never tracebacks (dispatch did NOT catch this before).
        print(f"schema error: {e}", file=sys.stderr)
        return 2
    except schema_cache.CacheWriteError as e:
        # The persistent schema cache is unwritable (classically a root-owned ~/.uedctl/cache from a
        # container run). Surfaced with an actionable fix, never swallowed — a dead cache otherwise
        # re-decodes every package every run with no hint why (2026-07-18). The message is
        # self-contained (chown hint + UEDCTL_SCHEMA_CACHE=off escape hatch).
        print(str(e), file=sys.stderr)
        return 2
    except BrokenPipeError:
        # stdout consumer went away (`uedctl … | head`) — the conventional silent exit, not an
        # error. Detach stdout so the interpreter's shutdown flush can't re-raise into noise.
        sys.stdout = open(os.devnull, "w")
        return 0
    except OSError as e:
        # Filesystem backstop (read-only checkout, a managed-dir key pointing at a file, a full
        # disk, …): the message names the path; a raw PermissionError/NotADirectoryError traceback
        # must never reach the user (review fix, 2026-07-18). Ordered AFTER TimeoutError (an
        # OSError subclass) so editor timeouts keep their specific message.
        print(f"filesystem error: {e}", file=sys.stderr)
        return 2


def _dispatch(args) -> int:
    # --- class group: offline class discovery (no editor, no ambient level needed) ---
    if args.cmd == "class":
        return _dispatch_class(args)


    # --- level group ---
    if args.cmd == "level" and args.sub == "materialize":
        return _level_materialize(args)

    if args.cmd == "level" and args.sub == "preview":
        return _level_preview(args)

    if args.cmd == "level" and args.sub == "doctor":
        return _level_doctor(args, _resolve_level_source(args))

    if args.cmd == "level" and args.sub == "create":
        return _level_create(args)
    if args.cmd == "level" and args.sub == "list":
        return _level_list(args)
    if args.cmd == "level" and args.sub == "status":
        return _level_status(args)

    # --- event group: read-only Tag<->Event wiring analysis over the current level (no editor) ---
    if args.cmd == "event" and args.sub == "graph":
        return _event_graph(args, _resolve_level_source(args))

    # --- project group: read-only project/search-path diagnostic (no ambient level needed) ---
    if args.cmd == "project" and args.sub == "show":
        return _project_show(args)

    # --- stash group: model-side register (capture/show/list/drop), no editor ---
    if args.cmd == "stash":
        return _dispatch_stash(args, _resolve_stash_register(args))

    # --- actor build: STATELESS generator — writes a point-actor T3D to stdout. ---
    if args.cmd == "actor" and args.sub == "build":
        from .emit import emit_actor_t3d
        from .model import Actor
        aclass = args.aclass
        parts = aclass.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise _SelectionExit(f"actor build: class must be Package.Name, got: {aclass!r}")
        _pkg, cls = parts
        at = tuple(args.at) if args.at else (0.0, 0.0, 0.0)
        # --prop adopts the `actor prop set` grammar + schema validation (spec §7): tokens
        # compose onto the class-default base (a member edit materializes the default
        # explicitly); a Location token routes to the typed field, overriding --at. Grammar
        # errors surface before anything else (matching the old KEY=VALUE pre-check).
        try:
            toks = [propedit.parse_token(t, expect_value=True) for t in (args.prop or [])]
        except propedit.PropEditError as e:
            raise _SelectionExit(f"actor build: {e}") from None
        actor = Actor(name=args.base_name or cls, cls=aclass, location=at, props=[], brush=None)
        _validate_ingest_actors([actor], args)          # existence-validate the class before emit
        if toks:
            try:
                plan = propedit.plan_edit(actor, toks, "set", _class_ctx(aclass, args),
                                          propedit.TYPED_FIELDS)
            except propedit.PropEditError as e:
                raise _SelectionExit(f"actor build: {e}") from None
            except SchemaError as e:
                raise _SelectionExit(f"actor build: {e}") from None
            actor.props = plan.props
            for attr, val in plan.typed_updates.items():
                setattr(actor, attr, val)
            if actor.location is None:              # a whole `Location` unset → emit at the origin
                actor.location = (Decimal(0), Decimal(0), Decimal(0))
        # Feature 7: --rotate SETS the Rotation field absolutely (shorthand for --prop Rotation=…);
        # a point actor has no brush, so the off-grid warning never fires here.
        _apply_generator_rotate([actor], getattr(args, "rotate", None))
        _apply_generator_org([actor], args)             # --folder/--label → sidecar carriers
        sys.stdout.write(emit_actor_t3d(actor))
        return 0

    # --- brush build: STATELESS generator — writes T3D to stdout. ---
    if args.cmd == "brush" and args.sub == "build":
        from . import builders
        from .emit import emit_actor_t3d
        shape = args.shape
        mover_class = getattr(args, "mover_class", None)
        if mover_class is not None:
            parts = mover_class.split(".")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise _SelectionExit(
                    f"brush build: --mover-class must be Package.Name, got: {mover_class!r}")
            if args.csg is not None:
                raise _SelectionExit("brush build: --csg is invalid with --mover-class "
                                     "(a mover does not participate in world CSG)")
            if args.solidity is not None:
                raise _SelectionExit("brush build: --solidity is invalid with --mover-class "
                                     "(a mover's collision is not CSG solidity — set actor "
                                     "collision flags via --prop)")
        brush_or_list = _build_brushes(builders, shape, args)
        at = tuple(args.at) if args.at else (0.0, 0.0, 0.0)
        if mover_class is not None:
            name_template = args.base_name or mover_class.rsplit(".", 1)[-1]   # ElevatorMover/Mover
        else:
            name_template = args.base_name or shape.capitalize()
        poly_flags = builders.SOLIDITY_FLAGS.get(args.solidity or "solid", 0)
        csg = args.csg or "add"
        # Group is no longer a dedicated brush-build flag (ditched 2026-07-24 17:04) — set it via
        # --prop Group=<name>, applied below; so make_brush_actor gets group=None.
        if isinstance(brush_or_list, list) and len(brush_or_list) > 1:
            actors = [
                builders.make_brush_actor(f"{name_template}{k}", b, location=at, csg=csg,
                                          group=None, poly_flags=poly_flags,
                                          mover_class=mover_class)
                for k, b in enumerate(brush_or_list)
            ]
        else:
            b = brush_or_list[0] if isinstance(brush_or_list, list) else brush_or_list
            actors = [builders.make_brush_actor(name_template, b, location=at, csg=csg,
                                                group=None, poly_flags=poly_flags,
                                                mover_class=mover_class)]
        # --prop (M3): schema-validated actor properties, same grammar/validation as `actor build
        # --prop`, applied to EVERY emitted brush/mover actor (composing onto its generator props:
        # CsgOper/PolyFlags/Group/Brush). The way to set open-ended mover config (MoverEncroachType,
        # Tag/Event, collision flags) at birth. Grammar errors surface before schema resolution.
        prop_tokens = getattr(args, "prop", None) or []
        if prop_tokens:
            try:
                ptoks = [propedit.parse_token(t, expect_value=True) for t in prop_tokens]
            except propedit.PropEditError as e:
                raise _SelectionExit(f"brush build: {e}") from None
            ctxs: dict[str, propedit.ClassCtx] = {}
            for a in actors:
                ctx = ctxs.setdefault(a.cls.casefold(), _class_ctx(a.cls, args))
                try:
                    plan = propedit.plan_edit(a, ptoks, "set", ctx, propedit.TYPED_FIELDS)
                except propedit.PropEditError as e:
                    raise _SelectionExit(f"brush build: {e}") from None
                except SchemaError as e:
                    raise _SelectionExit(f"brush build: {e}") from None
                a.props = plan.props
                for attr, val in plan.typed_updates.items():
                    setattr(a, attr, val)
        # Feature 7: --rotate SETS the Rotation field absolutely on every emitted actor (identity
        # base ⇒ no add-vs-override ambiguity); warns off-grid. No-op when the flag is absent.
        # (After --prop so --rotate wins over a --prop Rotation=…, matching actor build.)
        _apply_generator_rotate(actors, getattr(args, "rotate", None))
        # AFTER --rotate, so rotation-induced off-grid geometry counts too. `_apply_generator_rotate`
        # emits its own rotation-specific warning; both may print, and they report different causes.
        _advise_swept_brush(shape, actors, mover_class=mover_class, poly_flags=poly_flags)
        _apply_generator_org(actors, args)             # --folder/--label → sidecar carriers
        # Author-time gate: existence-validate the class (Engine.Brush or --mover-class) + the
        # --texture ref, if any, before emitting the T3D.
        _validate_ingest_actors(actors, args)
        for a in actors:
            sys.stdout.write(emit_actor_t3d(a))
        return 0

    # --- brush intersect/deintersect: STATELESS generator over a piped brush SET. ---
    if args.cmd == "brush" and args.sub in ("intersect", "deintersect"):
        return _brush_merge(args)

    # --- prefab group: tier-2 library. Reads touch only the tracked dir; `prefab apply`
    # resolves its own trunk level source inside _dispatch_prefab. ---
    if args.cmd == "prefab":
        return _dispatch_prefab(args)

    # --- texture group: substrate utility — pure offline UCC batchexport, no live editor,
    # no model touch. ---
    if args.cmd == "texture":
        return _dispatch_texture(args)
    if args.cmd == "substrate":
        return _dispatch_substrate(args)
    if args.cmd == "cache":
        return _dispatch_cache(args)

    # Folder surfaces are trunk-only — reject `--target stash|prefab` BEFORE resolving the source, so
    # the message is the right one (a stash/prefab source would otherwise resolve fine, then drop the
    # sidecar / query an always-None dimension). Guards `actor folder …`, `actor add --folder`, and
    # `actor find --folder/--no-folder` (spec §4).
    if args.cmd == "actor" and args.sub == "folder":
        _reject_nonlevel_target_for_folders(args)
    if (args.cmd == "actor" and args.sub == "find"
            and (getattr(args, "folder", None) or getattr(args, "no_folder", False))):
        _reject_nonlevel_target_for_folders(args)
    # Labels are trunk-only THIS slice (plan scope-cut) — reject `--tree stash|prefab` before
    # resolving the source, mirroring the folder guards above. `actor label …` always; `actor add
    # --label` and `actor find --label/--no-label` when a label surface is actually used.
    if args.cmd == "actor" and args.sub == "label":
        _reject_nonlevel_target_for_labels(args)
    if (args.cmd == "actor" and args.sub == "find"
            and (getattr(args, "label", None) or getattr(args, "no_label", False))):
        _reject_nonlevel_target_for_labels(args)
    if (args.cmd == "actor" and args.sub == "add"
            and getattr(args, "label", None)):
        _reject_nonlevel_target_for_labels(args)
    # `duplicate` ALWAYS mints a fresh dup-<rand> batch label, and the stash/prefab box save carries
    # no labels channel (deferred scope-cut) — so it rejects stash/prefab UNCONDITIONALLY (not only
    # with an explicit --label), else the batch label would silently vanish on a box save.
    if args.cmd == "actor" and args.sub == "duplicate":
        _reject_nonlevel_target_for_labels(args)
    # `is not None` (not truthiness) so `--folder ""` still routes to the folder-guard message on a
    # stash/prefab target (it's still an invalid path — validate_folder_path rejects it later). The
    # CARRIER path (an incoming `// uedctl-folder:` with no explicit --folder) is guarded separately
    # in the add handler, where the parsed folders are known (review 2026-07-18).
    if (args.cmd == "actor" and args.sub in ("add", "duplicate")
            and getattr(args, "folder", None) is not None):
        _reject_nonlevel_target_for_folders(args)
    # CSG ordering is trunk-only too (spec §7). `actor order` always; `actor add --order` only when a
    # non-default placement is requested (`last` == today's append, valid on any target).
    if args.cmd == "actor" and args.sub == "order":
        _reject_nonlevel_target_for_order(args)
    if (args.cmd == "actor" and args.sub == "add"
            and (getattr(args, "order", "last") or "last").strip().casefold() != "last"):
        _reject_nonlevel_target_for_order(args)

    # `actor preview --from-t3d` renders the given snippet(s) with NO level: it needs a project (for
    # the point-actor schema/texture resolver, which tolerates its absence) but never an ambient
    # $UEDCTL_LEVEL, so it must run BEFORE the eager level-source resolution below.
    if args.cmd == "actor" and args.sub == "preview" and getattr(args, "from_t3d", None):
        return _preview_from_t3d(args)

    # Every remaining verb (reads included) resolves the trunk level source — the ambient $UEDCTL_LEVEL in a
    # uedctl project. No project ⇒ a clean `_ProjectError` (exit 2), not a traceback.
    src = _resolve_level_source(args)

    if args.cmd == "actor" and args.sub == "folder":
        return _actor_folder(args, src)

    if args.cmd == "actor" and args.sub == "label":
        return _actor_label(args, src)

    if args.cmd == "mover" and args.sub == "key":
        return _dispatch_mover_key(args, src)

    # --- query verbs (no mutation) ---
    if args.cmd == "actor" and args.sub == "find":
        find_folders = getattr(args, "folder", None) or []
        find_no_folder = getattr(args, "no_folder", False)
        for pat in find_folders:                          # globstar grammar-check → exit 2 (spec §3)
            try:
                folderlib.validate_pattern(pat)
            except ValueError as e:
                raise _SelectionExit(str(e))
        find_labels = getattr(args, "label", None) or []
        find_no_label = getattr(args, "no_label", False)
        for pat in find_labels:                           # flat `*`-only grammar-check → exit 2 (spec §5)
            try:
                labellib.match_label(pat, "")             # reject `?`/`[`/`]`; the match result is discarded
            except ValueError as e:
                raise _SelectionExit(str(e))
        level = src.load()
        if getattr(args, "exclude", False) and getattr(args, "restrict", None) != "-":
            raise _SelectionExit("--exclude requires - (a piped name-set to exclude from)")
        if getattr(args, "restrict", None) not in (None, "-"):
            raise _SelectionExit(f"find takes no positional name; use --name (got {args.restrict!r})")
        class_filter = _find_class_filter(args, level)    # --exact-class ∪ --subclass-of expansion
        names = query.list_actors(
            level,
            names=args.name or None,
            classes=class_filter,
            groups=args.group or None,
            folders=find_folders or None,
            no_folder=find_no_folder,
            labels=find_labels or None,
            no_label=find_no_label,
            kind=args.kind,
        )
        if args.prop:
            # EFFECTIVE-value matching (spec §7, ruling R3): each --prop token matches what
            # `actor prop get` would print — stored value, else class default, else zero —
            # compared type-aware. A key not declared on a GIVEN actor's class is a per-actor
            # no-match; a key declared on NO considered class is a typo → exit 2; an
            # unbuildable class schema is a hard error (no-fallback). Plain `find` without
            # --prop never touches the schema.
            try:
                toks = [propedit.parse_token(t, expect_value=True) for t in args.prop]
            except propedit.PropEditError as e:
                print(str(e), file=sys.stderr)
                return 2
            ctxs: dict[str, propedit.ClassCtx] = {}
            declared: dict[str, bool] = {t.raw: False for t in toks}
            matched: list[str] = []
            try:
                for n in names:
                    actor = level.actors[n]
                    ctx = ctxs.setdefault(actor.cls.casefold(), _class_ctx(actor.cls, args))
                    ok = True
                    for t in toks:
                        r = propedit.effective_match(actor, t, ctx, propedit.TYPED_FIELDS)
                        if r is None:                # class doesn't declare the key
                            ok = False
                        else:
                            declared[t.raw] = True
                            ok = ok and r
                    if ok:
                        matched.append(n)
                # Typo protection (ruling R3): a key declared on NO class → exit 2. Checked
                # over the considered actors' classes; with an EMPTY considered set, fall back
                # to every class in the level so `find --name zzz --prop Typoo=1` still flags
                # the typo (review finding — the guard used to be skipped entirely).
                undeclared = [t for t in toks if not declared[t.raw]]
                if undeclared and not names:
                    for a in level.actors.values():
                        ctx = ctxs.setdefault(a.cls.casefold(), _class_ctx(a.cls, args))
                        for t in list(undeclared):
                            if t.base.casefold() in propedit.TYPED_FIELDS or                                     ctx.schema().get(t.base.casefold()) is not None:
                                declared[t.raw] = True
                                undeclared.remove(t)
                        if not undeclared:
                            break
            except propedit.PropEditError as e:
                print(f"--prop: {e}", file=sys.stderr)
                return 2
            except SchemaError as e:
                print(str(e), file=sys.stderr)
                return 2
            if level.actors:                         # typo protection (empty level: nothing to say)
                for t in toks:
                    if not declared[t.raw]:
                        print(f"--prop {t.raw}: no considered actor's class declares "
                              f"{t.base}", file=sys.stderr)
                        return 2
            names = matched
        # Spatial filter (spec 2026-07-24-find-spatial): `--within-bbox` keeps actors whose world AABB
        # is fully inside the given box. AABB predicate over `writes.actor_bounds` (full transform,
        # Decimal), in the handler AFTER list_actors — ANDs with the other filters, alongside --prop,
        # before the composable-find restrict. In-tree order preserved.
        bbox = getattr(args, "within_bbox", None)
        if bbox is not None:
            names = [n for n in names
                     if writes.aabb_within(writes.actor_bounds(level.actors[n]), bbox)]
        # Composable-find grep/universe model (spec 2026-07-24-composable-find): `-` makes the piped
        # name-set the universe; the filters above are the predicate; --exclude negates it. Applied to
        # the FINAL `names` (post --prop), in-tree order preserved.
        if getattr(args, "restrict", None) == "-":
            raw = _resolve_target_names(["-"])
            try:
                universe = set(query.resolve_actor_names(level, raw))   # strict, all-or-nothing
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            matched_set = set(names)
            keep = universe - matched_set if getattr(args, "exclude", False) else universe & matched_set
            names = [n for n in query.list_actors(level) if n in keep]
        if getattr(args, "json", False):
            import json
            print(json.dumps(names, indent=2))
        else:
            for n in names:
                print(n)
        return 0

    if args.cmd == "actor" and args.sub == "show":
        # By default each block carries `// uedctl-folder:`/`// uedctl-labels:` comments (importable
        # T3D that also round-trips the sidecars through `actor add -`); `--t3d-only` suppresses them.
        with_sidecars = not getattr(args, "t3d_only", False)
        # `-` (a stdin name list) is intercepted BEFORE the glob path — `show`'s name is otherwise
        # glob-capable, a SEPARATE multi-actor mechanism (spec §8).
        if args.name == "-":
            raw = _resolve_target_names([args.name])
            if not raw:
                return 0                                  # empty stdin: no-op, exit 0
            level = src.load()
            try:
                names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            # Each block self-identifies via its `Name=`; concatenation is valid T3D (spec §3).
            print("\n".join(query.actor_show_block(level.actors[n], with_sidecars) for n in names))
            return 0
        level = src.load()                               # outside the guard, like the sibling verbs
        try:
            out = query.show_actor(level, args.name, with_sidecars=with_sidecars)
        except KeyError as e:                            # exact-name miss (globs return "" instead)
            print(e.args[0], file=sys.stderr)
            return 2
        print(out)
        return 0


    if args.cmd == "actor" and args.sub == "bbox":
        # Feature 5: world AABB enclosing the passed actors as ONE box (the multi-actor case IS the
        # union — no --union flag). `-` reads a name list from stdin; empty stdin is a clean no-op.
        raw = _resolve_target_names(args.names)
        if not raw:
            return 0                                      # empty stdin: no-op, exit 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)  # unknown name → clean exit 2 (below)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)             # "Actors not found: <names>" — no traceback
            return 2
        names = list(dict.fromkeys(resolved))
        actors = [level.actors[n] for n in names]
        lo, hi, size, center = _bbox_of(actors)
        vecs = {"min": lo, "max": hi, "size": size, "center": center}
        if getattr(args, "field", None) is not None:
            v = vecs[args.field]
            print(",".join(_fmt_coord_component(c) for c in v))
        elif getattr(args, "json", False):
            import json
            print(json.dumps({k: {"x": _num_coord_component(v[0]), "y": _num_coord_component(v[1]),
                                  "z": _num_coord_component(v[2])} for k, v in vecs.items()},
                             indent=2))
        else:
            for k in ("min", "max", "size", "center"):
                print(f"{k:<6} {','.join(_fmt_coord_component(c) for c in vecs[k])}")
        print(f"bbox of {len(actors)} actor(s)", file=sys.stderr)
        return 0

    if args.cmd == "brush" and args.sub == "poly" and args.polysub == "list":
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        if getattr(args, "json", False):
            import json
            print(json.dumps({"actor": canonical,
                              "polys": query.list_polys(level.actors[canonical])}, indent=2))
        else:
            print(query.format_polys(level.actors[canonical], canonical))
        return 0

    if args.cmd == "brush" and args.sub == "poly" and args.polysub == "set":
        from . import surface
        targets = _resolve_target_names(args.targets)    # `-` → stdin (BRUSH:idx lines from poly find)
        if not targets:
            return 0                                      # empty stdin / no targets: clean no-op
        _validate_texture_ref(args.texture, args)       # author-time: reject a fabricated ref
        level = src.load()
        try:
            touched = surface.apply_surface_edit(
                level, targets, texture_ref=args.texture,
                add_flags=args.add_flags, remove_flags=args.remove_flags,
                pan_to=args.pan_to, pan_by=args.pan_by)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        rec_args: dict = {"targets": targets}
        if args.texture is not None:
            rec_args["texture"] = args.texture
        if args.add_flags:
            rec_args["add_flags"] = args.add_flags
        if args.remove_flags:
            rec_args["remove_flags"] = args.remove_flags
        if args.pan_to is not None:
            rec_args["pan_to"] = [str(c) for c in args.pan_to]
        if args.pan_by is not None:
            rec_args["pan_by"] = [str(c) for c in args.pan_by]
        src.save(verb="poly-set", args=rec_args, level=level, touched=touched)
        for name in touched:                             # PRODUCER: touched brush names → stdout (feed `| verb -`)
            print(name)
        print(f"set on {len(touched)} brush(es)", file=sys.stderr)
        return 0

    if args.cmd == "brush" and args.sub == "poly" and args.polysub == "find":
        from . import polyalign
        facing = getattr(args, "facing", None)
        valid_facing = {"+X", "-X", "+Y", "-Y", "+Z", "-Z", "slant"}
        if facing is not None and facing not in valid_facing:
            print(f"brush poly find --facing: invalid value {facing!r} "
                  f"(expected one of {', '.join(sorted(valid_facing))})", file=sys.stderr)
            return 2
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        actor = level.actors[canonical]
        try:
            idxs = polyalign.find_faces(actor, canonical, item=args.item,
                                        facing=facing, texture=args.texture)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if getattr(args, "json", False):
            import json
            rows = []
            for i in idxs:
                p = actor.brush.polys[i]
                wv = polyalign._world_verts(actor, p)
                rows.append({"brush": canonical, "poly": i, "item": p.item,
                             "facing": query._poly_facing(wv) if len(wv) >= 3 else None,
                             "texture": p.texture})
            print(json.dumps(rows, indent=2))
        else:
            for i in idxs:
                print(f"{canonical}:{i}")
        print(f"{len(idxs)} face(s) matched", file=sys.stderr)
        return 0

    if args.cmd == "brush" and args.sub == "poly" and args.polysub == "align":
        from . import polyalign
        tokens = _resolve_target_names(args.targets)     # `-` → stdin (bare names or BRUSH:idx lines)
        if not tokens:
            return 0                                      # empty stdin / no targets: clean no-op
        level = src.load()
        try:
            touched = polyalign.align(level, tokens, args.mode,
                                      fresh_frame=args.fresh_frame,
                                      fit_perimeter=args.fit_perimeter)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        if not touched:
            return 0
        for name in touched:
            print(name)
        print(f"aligned {len(tokens)} face target(s) across {len(touched)} brush(es) "
              f"({args.mode})", file=sys.stderr)
        src.save(verb="poly-align", args={"mode": args.mode}, level=level, touched=touched)
        return 0

    if args.cmd == "brush" and args.sub == "vertex" and args.vsub == "list":
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        if getattr(args, "json", False):
            import json
            rows = []
            for r in query.list_vertices(level.actors[canonical]):
                c = r["coord"]
                rows.append({"coord": {"x": _num_coord_component(c[0]),
                                       "y": _num_coord_component(c[1]),
                                       "z": _num_coord_component(c[2])},
                             "polys": r["polys"], "nrefs": r["nrefs"]})
            print(json.dumps({"actor": canonical, "vertices": rows}, indent=2))
        else:
            print(query.format_vertices(level.actors[canonical], canonical))
        return 0

    # --- actor preview (model-only, host-side; reads the trunk level, no editor/container) ---
    # T3D mode (`--from-t3d`) is handled earlier, before level-source resolution (it needs no level).
    if args.cmd == "actor" and args.sub == "preview":
        raw = _resolve_target_names(args.names)             # `-` → names from stdin (spec §1)
        if not raw:
            return 0                                        # empty stdin: no-op, exit 0
        level = src.load()
        try:
            names = query.resolve_actor_names(level, raw)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        actors = [level.actors[n] for n in names]
        return _render_actors_to_out(actors, args)

    # --- mutate verbs: pure model-side transforms of main/, no editor (design D-F) ---
    if args.cmd == "actor" and args.sub == "move":
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        a = level.actors[canonical]
        loc = a.location or (Decimal(0), Decimal(0), Decimal(0))
        record_args = {"name": canonical}
        if args.to is not None:
            a.location = tuple(args.to)
            record_args["to"] = [str(c) for c in args.to]
        elif args.by is not None:
            a.location = tuple(loc[i] + args.by[i] for i in range(3))
            record_args["by"] = [str(c) for c in args.by]
        src.save(verb="move", args=record_args, level=level, touched=[canonical])
        print(canonical)                                 # PRODUCER: moved name → stdout (feed `| verb -`)
        print(f"moved {canonical}", file=sys.stderr)
        return 0

    if args.cmd == "actor" and args.sub == "order":
        # Reorder existing actors' CSG precedence by minting new order_values (spec 2026-07-18).
        # Trunk-only (guarded pre-resolve). The mutually-exclusive selector group is `required=True`.
        raw = _resolve_target_names(args.names)          # `-` → names from stdin (spec §7)
        if not raw:
            return 0                                      # empty stdin: no-op, exit 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)
        except KeyError as e:                            # unknown moved actor → exit 2 (all-or-nothing)
            print(e.args[0], file=sys.stderr)
            return 2
        moved = list(dict.fromkeys(resolved))            # dedupe on CANONICAL names, order-preserving
        if args.first:
            selector, ref = "first", None
        elif args.last:
            selector, ref = "last", None
        elif args.before is not None:
            selector, ref = "before", args.before
        else:
            selector, ref = "after", args.after
        if ref is not None:
            try:
                ref = query.resolve_actor_name(level, ref)   # --before/--after NAME must exist
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            if ref in set(moved):                        # ordering relative to self is undefined
                raise _SelectionExit(
                    f"actor order: cannot order relative to {ref} — it is in the moved set")
        try:                                             # src._ranks: the load-snapshot order_values
            override = order_ops.compute_reorder_ranks(src._ranks, moved, selector, ref)
        except ValueError as e:                          # adjacent/duplicate imported ranks — no gap
            raise _SelectionExit(f"cannot reorder: {e}")
        src.save(verb="order", args={"names": moved, "selector": selector, "ref": ref},
                 level=level, touched=moved, ranks=override)
        for name in moved:                               # PRODUCER: reordered names to stdout (feed `| verb -`)
            print(name)
        print(f"reordered {len(moved)} actor(s)", file=sys.stderr)
        return 0

    if args.cmd == "actor" and args.sub == "delete":
        raw = _resolve_target_names(args.names)          # `-` → names from stdin (spec §8)
        if not raw:
            return 0                                      # empty stdin: no-op, exit 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        # Dedupe on CANONICAL names (order-preserving): two differently-cased piped tokens are the
        # SAME actor, and a second `pop` would raise KeyError (spec §8).
        names = list(dict.fromkeys(resolved))
        for name in names:
            level.actors.pop(name)
        level.order = order_after_delete(level.order, names)
        src.save(verb="delete", args={"names": names},
                        level=level, touched=names)
        for name in names:                               # PRODUCER: deleted names → stdout (a log/count)
            print(name)
        print(f"deleted {len(names)} actor(s)", file=sys.stderr)
        return 0

    if args.cmd == "actor" and args.sub == "add":
        level = src.load()
        text = _read_t3d_input(args.file)
        # `actor add` is a PURE carrier-consumer (no --folder/--label as of 2026-07-24 17:04): the
        # `// uedctl-folder:`/`// uedctl-labels:` carriers in the T3D (set by the generator) win as-is;
        # there is no override channel. Post-hoc changes use `actor folder set` / `actor label`.
        return _ingest_actor_t3d(args, src, level, text, verb="add", labels_override=None)

    if args.cmd == "actor" and args.sub == "duplicate":
        # Sugar for `actor show <names…> | actor add -`: re-ingest the named actors' show-blocks
        # (folder + label carriers included so both round-trip) → fresh-named copies. `-` reads a
        # name list from stdin; empty stdin is a clean no-op. A REQUIRED --by/--at placement (argparse
        # enforces it) shifts the copies off their originals; every copy inherits the source labels
        # and gets ONE fresh dup-<rand> batch label so the batch is re-addressable afterwards.
        raw = _resolve_target_names(args.names)
        if not raw:
            return 0                                       # empty stdin: no-op, exit 0
        level = src.load()
        try:
            names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
        except KeyError as e:
            print(e.args[0], file=sys.stderr)              # "Actors not found: …" — never a traceback
            return 2
        # Apply the placement by translating the SOURCE actors before emitting their show-blocks, so
        # the copies' Locations are already correct when re-ingested (--by = per-actor delta; --at =
        # anchor the set's union bbox-min corner, shifting the whole set together).
        sources = [level.actors[n] for n in names]
        by = getattr(args, "by", None)
        at = getattr(args, "at", None)
        if by is not None:
            placed = stashlib.translate(sources, tuple(by))
        else:
            lo, _hi = writes.union_bounds(sources)
            placed = stashlib.translate(sources, tuple(a - b for a, b in zip(at, lo)))
        text = "\n".join(query.actor_show_block(a, with_sidecars=True) for a in placed)
        # Fresh batch token, re-rolled until it is not already a label anywhere in the level — so the
        # batch handle can't collide with a prior duplicate's still-live token.
        existing_labels = {lbl for a in level.actors.values() for lbl in a.labels}
        while (dup_token := f"dup-{t3dtree._rand_suffix()}") in existing_labels:
            pass
        labels_add = frozenset({dup_token}) | frozenset(getattr(args, "label", None) or [])
        rc = _ingest_actor_t3d(args, src, level, text, verb="duplicate", labels_add=labels_add)
        if rc == 0:                                        # only echo the batch label if the copy landed
            print(f"batch label: {dup_token}", file=sys.stderr)
        return rc

    if args.cmd == "actor" and args.sub == "prop":
        # `-` in the name position reads a newline name list from stdin → multi-actor mode; the
        # SAME tokens apply to every piped actor. Piped actors may be DIFFERENT classes, so the
        # class schema/defaults resolve per-actor. Single (non-`-`) name keeps today's behaviour
        # exactly (singular "Actor not found:" message, bare `get` output, `{"name": …}` record).
        piped = (args.name == "-")
        raw = _resolve_target_names([args.name])
        if not raw:
            return 0                                      # empty stdin: no-op, exit 0
        level = src.load()
        try:
            if piped:
                # Dedupe on CANONICAL names (spec §8): a repeated piped name is the same actor;
                # applying the edit twice would double-apply (or double-print for `get`).
                names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
            else:
                names = [query.resolve_actor_name(level, raw[0])]
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        actors = [level.actors[n] for n in names]
        # The class schema/defaults resolve LAZILY inside each ClassCtx (only when a token needs
        # them) — hard-rejects and typed-field-only invocations never require the v68 install
        # (spec §2.4). The four seams (_class_schema/_class_defaults/_struct_members/
        # _enum_names) are what tests mock.
        try:
            if args.propsub == "get":
                toks = [propedit.parse_token(t, expect_value=False) for t in args.tokens]
                want_json = getattr(args, "json", False)
                # JSON always renders the KV-form (KEY=VALUE) lines so each splits into a
                # (key, value) pair; the KEY (a prop name/dot-path) never contains `=`, so the
                # value keeps any embedded `=` (a struct like `(Pitch=0,…)`). Build EVERY actor's
                # lines first, then print — a bad token/class on a later actor leaves the whole
                # dump un-emitted (atomic), and `get` never partial-prints.
                kv = args.kv or piped or want_json
                per_actor: list[tuple[str, list[str]]] = []
                for actor, name in zip(actors, names):
                    ctx = _class_ctx(actor.cls, args)
                    if toks:
                        # Piped multi-actor output is name-prefixed KV (`<name>\t<key>=<value>`) so
                        # a dump over several keys stays parseable (spec §8); a single CLI name
                        # keeps today's bare (or `--kv`) output.
                        lines = propedit.get_lines(actor, toks, ctx, propedit.TYPED_FIELDS, kv=kv)
                    else:                            # dump-all: the stored view (spec §2.3)
                        lines = propedit.dump_all_lines(actor, ctx, propedit.TYPED_FIELDS)
                    per_actor.append((name, lines))
                if want_json:
                    import json

                    def _kv_obj(lines):
                        obj: dict[str, str] = {}
                        for ln in lines:
                            k, _, v = ln.partition("=")
                            obj[k] = v
                        return obj
                    # Piped read (`-`): {name: {key: value}}; a single named actor: flat {key: value}.
                    if piped:
                        print(json.dumps({name: _kv_obj(lines) for name, lines in per_actor},
                                         indent=2))
                    else:
                        print(json.dumps(_kv_obj(per_actor[0][1]) if per_actor else {}, indent=2))
                    return 0
                out_lines: list[str] = []
                for name, lines in per_actor:
                    out_lines.extend(f"{name}\t{ln}" if piped else ln for ln in lines)
                for ln in out_lines:
                    print(ln)
                return 0
            mode = args.propsub                      # "set" | "unset"
            toks = [propedit.parse_token(t, expect_value=(mode == "set"))
                    for t in args.tokens]
            # TWO-PHASE (spec §8): plan EVERY actor before mutating ANY, so a bad token leaves ALL
            # actors untouched (validate-before-mutate across the whole piped set, cross-class).
            plans = [propedit.plan_edit(actor, toks, mode, _class_ctx(actor.cls, args),
                                        propedit.TYPED_FIELDS)
                     for actor in actors]
        except propedit.PropEditError as e:
            print(str(e), file=sys.stderr)
            return 2
        except SchemaError as e:
            print(str(e), file=sys.stderr)
            return 2
        for actor, plan in zip(actors, plans):
            for w in plan.warnings:
                print(f"warning: {w}", file=sys.stderr)
            actor.props = plan.props
            for attr, val in plan.typed_updates.items():
                setattr(actor, attr, val)
        # Single (non-`-`) name keeps the `{"name": …}` record shape (tests + callers depend on it);
        # multi-actor records `{"names": […]}`.
        rec = {"names": names} if piped else {"name": names[0]}
        rec.update(propsub=args.propsub, tokens=list(args.tokens))
        src.save(verb="prop", args=rec, level=level, touched=names)
        for name in names:                               # PRODUCER: touched names → stdout (feed `| verb -`)
            print(name)
        print(f"{mode} on {len(names)} actor(s)", file=sys.stderr)
        return 0

    def _warn_rotate_postscale_distortion(actor):
        # Rotating a NON-UNIFORM PostScale brush warps it — PostScale is world/post-rotation, so
        # old→new is a shear-conjugated rotation `PostScale·R·PostScale⁻¹` (spec §7). Inherent UE1
        # behavior (UnrealEd's own gizmo distorts it identically, silently). Warn, don't block.
        ps = rotation.actor_post_scale(actor)
        axes = [Decimal(str(c)) for c in ps.scale]
        if not (axes[0] == axes[1] == axes[2]):
            print(f"warning: {actor.name} has a non-uniform PostScale — rotating it WARPS the brush "
                  f"(PostScale is post-rotation; UnrealEd distorts it identically). Consider "
                  f"apply-transform first", file=sys.stderr)

    if args.cmd == "actor" and args.sub == "rotate":
        raw = _resolve_target_names(args.names)          # `-` → names from stdin (spec §8)
        if not raw:
            return 0                                      # empty stdin: no-op, exit 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        # Dedupe on CANONICAL names (order-preserving): a repeated name is the SAME actor
        # object, and applying the orbit + field-add twice would double-rotate it.
        names = list(dict.fromkeys(resolved))
        targets = [level.actors[n] for n in names]
        if getattr(args, "to", None) is not None:
            # ABSOLUTE rotation (--to): set the Rotation field IN PLACE (Location never moves;
            # excludes --pivot — spec §4). Each actor's field is replaced with the target value.
            if args.pivot is not None or args.pivot_actor is not None:
                print("actor rotate --to is in-place and cannot take a --pivot/--pivot-actor",
                      file=sys.stderr)
                return 2
            to_uu = tuple(rotation.uu_field(c) for c in args.to)
            for actor in targets:
                _warn_rotate_postscale_distortion(actor)
                props = [(k, v) for k, v in actor.props if k != "Rotation"]
                # ALWAYS written, `--to 0,0,0` included: an omitted `Rotation` does not mean
                # "unrotated", it means "whatever the CLASS defaults to" — and `TNM.LavaSpitter`
                # defaults `(Pitch=16384,Yaw=0,Roll=0)`, so dropping the prop here used to build it
                # pitched 90° with the post-verify passing (both compare sides shared the mistake).
                props.append(("Rotation", f"(Pitch={to_uu[0]},Yaw={to_uu[1]},Roll={to_uu[2]})"))
                actor.props = props
                if actor.brush is not None:
                    validate_brush(actor.brush)
            for name in names:                           # PRODUCER: rotated names to stdout (feed `| verb -`)
                print(name)
            print(f"rotated {len(targets)} actor(s) to {tuple(str(c) for c in args.to)}",
                  file=sys.stderr)
            src.save(verb="rotate", args={"names": names, "to": [str(c) for c in args.to]},
                     level=level, touched=names)
            return 0
        if args.pivot is not None:
            pivot = args.pivot
        elif args.pivot_actor is not None:
            try:
                pivot_canonical = query.resolve_actor_name(level, args.pivot_actor)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            pivot = level.actors[pivot_canonical].location or (Decimal(0), Decimal(0), Decimal(0))
        else:
            pivot = rotation.best_grid_pivot(targets)
        delta_uu = tuple(rotation.uu_field(c) for c in args.by)
        # Orbit with the SAME quantized delta the actors store, via the GMath table — so Location and
        # the stored Rotation are consistent AND match what the editor renders (not float degrees).
        R = rotation.euler_to_matrix_uu(*delta_uu)
        for actor in targets:
            _warn_rotate_postscale_distortion(actor)
            loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
            actor.location = rotation.rotate_point(loc, R, pivot)
            new_uu = rotation.compose_uu(delta_uu, rotation.actor_rotation_uu(actor))
            props = [(k, v) for k, v in actor.props if k != "Rotation"]
            # Written even when the composed result is (0,0,0) — see the `--to` note above: an
            # omitted `Rotation` re-imports as the CLASS DEFAULT, which is non-zero for
            # `TNM.LavaSpitter`, so "don't write a spurious Rotation=(0,0,0)" silently rotated it.
            props.append(("Rotation", f"(Pitch={new_uu[0]},Yaw={new_uu[1]},Roll={new_uu[2]})"))
            actor.props = props
            if actor.brush is not None:
                validate_brush(actor.brush)     # rigid → local geometry still valid
        for name in names:                               # PRODUCER: rotated names to stdout (feed `| verb -`)
            print(name)
        print(f"rotated {len(targets)} actor(s) about {tuple(str(c) for c in pivot)}",
              file=sys.stderr)
        src.save(verb="rotate",
                        args={"names": names, "by": [str(c) for c in args.by],
                              "pivot": [str(c) for c in pivot]},
                        level=level, touched=names)
        return 0

    if args.cmd == "brush" and args.sub == "scale":
        from . import movers, transform
        raw = _resolve_target_names(args.names)          # `-` → names from stdin
        if not raw:
            return 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        names = list(dict.fromkeys(resolved))            # dedupe: scaling twice would double-apply
        # `brush` verb (renamed from `actor scale`): MainScale is a brush-family property, so reject a
        # non-brush (point) actor up front, all-or-nothing — like the other brush verbs.
        nonbrush = [n for n in names if level.actors[n].brush is None]
        if nonbrush:
            print(f"brush scale: not a brush: {', '.join(nonbrush)} — MainScale is a brush property "
                  f"(a mesh scales via DrawScale, e.g. `actor prop set … DrawScale=…`)",
                  file=sys.stderr)
            return 2
        targets = [level.actors[n] for n in names]
        factors = args.to if args.to is not None else args.by
        # Disallow a zero / sub-epsilon scale factor — it collapses the brush to a plane and makes the
        # transform non-invertible (spec §7). Named exit-2, never a downstream crash.
        for c in factors:
            if abs(Decimal(c)) < transform.SCALE_EPS:
                print(f"brush scale: scale factor {tuple(str(x) for x in factors)} has a "
                      f"zero/sub-epsilon component — refusing (would collapse the brush)",
                      file=sys.stderr)
                return 2
        uniform = factors[0] == factors[1] == factors[2]
        # `--to` is an ABSOLUTE, IN-PLACE MainScale target (Location never moves), so a pivot is
        # meaningless with it (spec §4). This is one of the cheap argument checks, so it belongs
        # ABOVE the resolver — otherwise `brush scale --to … --pivot …` with no games config blames
        # the missing config instead of the conflicting flags the user actually typed.
        if args.to is not None and (args.pivot is not None or args.pivot_actor is not None):
            print("brush scale --to is in-place and cannot take a --pivot/--pivot-actor",
                  file=sys.stderr)
            return 2
        # Same reason: `--pivot-actor` names an actor in the ALREADY-LOADED level, so resolving it is
        # as cheap as the checks above — and a typo'd pivot name must say `Actor not found: …`, not
        # blame a missing games config.
        pivot_actor_loc = None
        if args.pivot_actor is not None:
            try:
                pivot_canonical = query.resolve_actor_name(level, args.pivot_actor)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            pivot_actor_loc = (level.actors[pivot_canonical].location
                               or (Decimal(0), Decimal(0), Decimal(0)))
        # AFTER every cheap argument check above (so a bad factor, a flag conflict or an unknown
        # pivot actor reports itself, not a missing resolver) and once per invocation, not per actor.
        mover_index = _mover_index(args, "brush scale")
        if args.to is not None:
            for actor in targets:
                cur = rotation.actor_main_scale(actor)
                actor.main_scale = transform.FScale(tuple(Decimal(c) for c in args.to),
                                                    cur.sheer_rate, cur.sheer_axis)
                if movers.is_mover(actor, mover_index):
                    print(f"warning: {actor.name} is a Mover — its keyframe travel (KeyPos/KeyRot) "
                          f"does not scale with the brush", file=sys.stderr)
                if not rotation.actor_post_scale(actor).is_identity():
                    print(f"warning: {actor.name} has a non-identity PostScale — the previewed world "
                          f"scale is PostScale*MainScale, not {tuple(str(c) for c in args.to)}",
                          file=sys.stderr)
                if actor.brush is not None:
                    validate_brush(actor.brush)
            for name in names:                           # PRODUCER: scaled names to stdout (feed `| verb -`)
                print(name)
            print(f"scaled {len(targets)} actor(s) to {tuple(str(c) for c in args.to)}",
                  file=sys.stderr)
            src.save(verb="scale", args={"names": names, "to": [str(c) for c in args.to]},
                     level=level, touched=names)
            return 0
        # RELATIVE (--by): multiply MainScale per-axis AND orbit each Location component-wise about
        # the pivot (`Loc' = P + S∘(Loc−P)` — NOT the rotation orbit; spec §10).
        if args.pivot is not None:
            pivot = args.pivot
        elif pivot_actor_loc is not None:                # resolved above, BEFORE the class resolver
            pivot = pivot_actor_loc
        else:
            pivot = rotation.best_grid_pivot(targets)
        S = tuple(Decimal(c) for c in args.by)
        for actor in targets:
            loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
            actor.location = tuple(pivot[i] + (loc[i] - pivot[i]) * S[i] for i in range(3))
            cur = rotation.actor_main_scale(actor)
            actor.main_scale = transform.FScale(
                tuple(Decimal(cur.scale[i]) * S[i] for i in range(3)), cur.sheer_rate, cur.sheer_axis)
            if movers.is_mover(actor, mover_index):
                print(f"warning: {actor.name} is a Mover — its keyframe travel (KeyPos/KeyRot) does "
                      f"not scale with the brush", file=sys.stderr)
            if not uniform and not rotation.is_identity_uu(rotation.actor_rotation_uu(actor)):
                print(f"warning: {actor.name} is rotated and scaled non-uniformly about a world "
                      f"pivot — MainScale is pre-rotation, so the world pivot orbit is inexact "
                      f"(consider apply-transform first)", file=sys.stderr)
            if actor.brush is not None:
                validate_brush(actor.brush)
        for name in names:                               # PRODUCER: scaled names to stdout (feed `| verb -`)
            print(name)
        print(f"scaled {len(targets)} actor(s) about {tuple(str(c) for c in pivot)}",
              file=sys.stderr)
        src.save(verb="scale",
                 args={"names": names, "by": [str(c) for c in args.by],
                       "pivot": [str(c) for c in pivot]},
                 level=level, touched=names)
        return 0

    if args.cmd == "brush" and args.sub == "apply-transform":
        from . import movers, transform
        raw = _resolve_target_names(args.names)
        if not raw:
            return 0
        level = src.load()
        try:
            resolved = query.resolve_actor_names(level, raw)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        names = list(dict.fromkeys(resolved))
        targets = [(n, level.actors[n]) for n in names]
        # `brush` verb (renamed from `actor apply-transform`): the bake folds into the PolyList, so a
        # non-brush (point) actor has nothing to bake — reject up front, all-or-nothing.
        nonbrush = [n for n, a in targets if a.brush is None]
        if nonbrush:
            print(f"brush apply-transform: not a brush: {', '.join(nonbrush)} — the bake folds the "
                  f"transform into brush vertices; a point actor has none", file=sys.stderr)
            return 2
        # Guards all-or-nothing (spec §7): a Mover bake rewrites PrePivot (= the swing axis) and
        # desyncs KeyPos/KeyRot — reject before mutating anything.
        mover_index = _mover_index(args, "brush apply-transform")
        movers_hit = [n for n, a in targets if movers.is_mover(a, mover_index)]
        if movers_hit:
            print(f"brush apply-transform: refusing to bake Mover(s) {', '.join(movers_hit)} — a "
                  f"bake rewrites PrePivot (the swing axis) and desyncs keyframe travel (deferred "
                  f"in v1); scale/rotate a mover in place instead", file=sys.stderr)
            return 2
        for n, a in targets:
            if not rotation.actor_post_scale(a).is_identity():
                print(f"warning: {n} has a non-identity PostScale — baking it is DESTRUCTIVE and "
                      f"IRREVERSIBLE (v1 has no PostScale-authoring verb to reconstruct it)",
                      file=sys.stderr)
        for n, a in targets:
            baked = transform.bake(a, lock_textures=args.lock_textures)
            if baked.brush is not None:
                validate_brush(baked.brush)
            level.actors[n] = baked
        for name in names:                               # PRODUCER: baked names to stdout (feed `| verb -`)
            print(name)
        print(f"baked {len(targets)} actor(s)", file=sys.stderr)
        src.save(verb="apply-transform",
                 args={"names": names, "lock_textures": bool(args.lock_textures)},
                 level=level, touched=names)
        return 0

    if args.cmd == "brush" and args.sub == "clip":
        from . import clip as clipmod
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        actor = level.actors[canonical]
        if actor.brush is None:
            print(f"{canonical} is not a brush", file=sys.stderr)
            return 2
        if args.plane is not None:
            point, normal = args.plane                # two X,Y,Z triples
        elif args.axis is not None and args.coord is not None:
            point, normal = clipmod.axis_plane(args.axis, args.coord)
        else:
            print("brush clip needs --axis AXIS --coord N, or --plane PX PY PZ NX NY NZ",
                  file=sys.stderr)
            return 2
        # The plane is world-space; map it into the brush's LOCAL frame (vertices are local):
        # point via `Rᵀ·(point − Location) + PrePivot`, normal via `Rᵀ·normal`. For a rotated brush
        # this clips the local PolyList by the de-rotated plane and the Rotation field is preserved,
        # so it materializes as the intended world clip. clip computes in float; world_to_local_*
        # handle the rotated/PrePivot inverse (and avoid the --axis float-minus-Decimal TypeError).
        local_point = rotation.world_to_local_point(actor, point)
        local_normal = rotation.world_to_local_normal(actor, normal)
        keep_negative = args.keep == "below"     # below = opposite the normal (orientation preserved)
        if clipmod.classify_clip(actor.brush, local_point, local_normal,
                                 keep_negative=keep_negative) == "whole":
            # Plane misses the brush interior (whole brush on the kept side) → a silent no-op before.
            print(f"clip plane did not intersect brush {canonical} — left unchanged",
                  file=sys.stderr)
            return 0
        actor.brush = clipmod.clip_brush(actor.brush, local_point, local_normal,
                                         keep_negative=keep_negative)
        validate_brush(actor.brush)
        # Stringify coords for the JSON command log (Decimal isn't JSON-serializable; --plane gives
        # Decimal point/normal). Matches `actor rotate`/`vertex move` recording.
        src.save(verb="clip",
                        args={"name": canonical,
                              "plane": [str(c) for c in (*point, *normal)], "keep": args.keep},
                        level=level, touched=[canonical])
        return 0

    if args.cmd == "brush" and args.sub == "replace":
        # In-place SHAPE SWAP: take ONLY the incoming PolyList; keep the target's Name, order_value
        # (CSG rank), Group, CsgOper, PolyFlags, Rotation, AND its old Location/PrePivot. The incoming
        # shape's own Location/PrePivot/Name are ignored (decisions 2026-07-18; supersedes `brush
        # resize`). `-` is the SOLE shape source (the `build → add -` T3D-snippet stdin convention).
        if args.shape != "-":
            print("brush replace: the shape argument must be `-` (read a T3D snippet from stdin, "
                  "e.g. `brush build cube … | brush replace NAME -`)", file=sys.stderr)
            return 2
        text = sys.stdin.read()
        if not text.strip():
            return 0                                       # empty stdin: clean no-op, exit 0
        # parse_t3d_actors (NOT parse_t3d) + drop the transient builder brush, exactly like `actor
        # add -`. A generator brush carries an explicit CsgOper so it is NOT filtered.
        incoming = [a for a in parse_t3d_actors(text)
                    if a.brush is not None and not is_builder_brush(a)]
        if not incoming:
            print("brush replace: no brush geometry found in the T3D input (nothing to swap in)",
                  file=sys.stderr)
            return 2
        if len(incoming) > 1:
            print(f"brush replace: stdin has {len(incoming)} brush actors, expected exactly one "
                  f"(a single-shape swap is unambiguous; pipe one `brush build <shape>`)",
                  file=sys.stderr)
            return 2
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        target = level.actors[canonical]
        if target.brush is None:
            print(f"{canonical} is not a brush", file=sys.stderr)
            return 2
        # Swap the polys only — keep the target Brush object so its model_name stays `Model_<name>`
        # (matches the actor's `Brush=` prop) and every other actor field (Location/PrePivot/props)
        # is untouched. validate_brush rejects degenerate incoming geometry before the write.
        target.brush.polys = incoming[0].brush.polys
        validate_brush(target.brush)
        src.save(verb="replace", args={"name": canonical}, level=level, touched=[canonical])
        return 0

    if args.cmd == "brush" and args.sub == "vertex" and args.vsub == "move":
        from . import vertex as vertexmod
        level = src.load()
        try:
            canonical = query.resolve_actor_name(level, args.name)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        actor = level.actors[canonical]
        if actor.brush is None:
            print(f"{canonical} is not a brush", file=sys.stderr)
            return 2
        # --at/--to are world positions → local via `Rᵀ·(world − Location) + PrePivot` (the inverse
        # of `vertex list`'s forward transform, so a coord copied from there round-trips). --by is a
        # world delta → local via `Rᵀ·delta` (rotation only). For a rotated brush the corner match
        # relies on emit.clean snapping the float-inverted coord to its grid corner.
        local_at = [rotation.world_to_local_point(actor, at) for at in args.at]
        if args.to is not None:
            local_to = rotation.world_to_local_point(actor, args.to)
            actor.brush = vertexmod.move_vertices(actor.brush, local_at, to=local_to)
        else:
            actor.brush = vertexmod.move_vertices(
                actor.brush, local_at, by=rotation.world_to_local_delta(actor, args.by))
        validate_brush(actor.brush)
        rec_args = {"name": canonical, "at": [[str(c) for c in at] for at in args.at]}
        if args.to is not None:
            rec_args["to"] = [str(c) for c in args.to]
        else:
            rec_args["by"] = [str(c) for c in args.by]
        src.save(verb="vertex-move", args=rec_args,
                        level=level, touched=[canonical])
        return 0

    print(f"unhandled verb: {args.cmd}/{getattr(args, 'sub', '')}", file=sys.stderr)
    return 2
