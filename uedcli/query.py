"""Query verbs answered from the in-memory model — instant, no editor."""
from __future__ import annotations

import fnmatch
import math
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from .model import Actor, Level
from .normalize import canonical_actor_t3d
from .preview import _face_normal

# PolyFlags bit → name (verify against the editor's Surface-Flags ref before relying on
# the higher bits). The CLI uses these names so the LLM never sees raw bit values.
PF_NAMES: list[tuple[int, str]] = [
    (0x1, "invisible"), (0x2, "masked"), (0x4, "translucent"), (0x8, "notsolid"),
    (0x10, "environment"), (0x20, "semisolid"), (0x40, "modulated"), (0x80, "fakebackdrop"),
    (0x100, "twosided"), (0x200, "autoupan"), (0x400, "autovpan"), (0x800, "nosmooth"),
    (0x100000, "speciallit"), (0x400000, "unlit"), (0x4000000, "portal"), (0x8000000, "mirror"),
]


def decode_flags(flags: int) -> list[str]:
    """Decode a PolyFlags int to flag names ('none' if 0; hex tail for unknown bits)."""
    names = [name for bit, name in PF_NAMES if flags & bit]
    known = sum(bit for bit, _ in PF_NAMES if flags & bit)
    if flags & ~known:
        names.append(hex(flags & ~known))
    return names or ["none"]


def _poly_facing(verts3d) -> str:
    """Snap a face's outward normal to ±X/±Y/±Z, or 'slant' if not near an axis."""
    n = _face_normal(verts3d)
    m = math.sqrt(sum(c * c for c in n)) or 1.0
    u = [c / m for c in n]
    axes = [("+X", (1, 0, 0)), ("-X", (-1, 0, 0)), ("+Y", (0, 1, 0)),
            ("-Y", (0, -1, 0)), ("+Z", (0, 0, 1)), ("-Z", (0, 0, -1))]
    name, axis = max(axes, key=lambda a: sum(u[i] * a[1][i] for i in range(3)))
    return name if sum(u[i] * axis[i] for i in range(3)) > 0.98 else "slant"


def list_polys(actor: Actor) -> list[dict]:
    """Per-poly metadata for surface identification: index, facing, texture, flags
    (decoded), world centroid, area, vertex count."""
    from .rotation import actor_linear, actor_prepivot, local_offset

    rows: list[dict] = []
    if not actor.brush:
        return rows
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    R = actor_linear(actor)        # full L (rotation+scale); None for identity → v unchanged
    prepivot = actor_prepivot(actor)
    for idx, poly in enumerate(actor.brush.polys):
        # honour the Rotation field + PrePivot (world geometry); to float for normal/area math.
        wv = [local_offset(R, prepivot, v) for v in poly.vertices]
        v3 = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2])) for w in wv]
        nv = len(v3)
        cen = tuple(round(sum(p[i] for p in v3) / nv) for i in range(3)) if nv else (0, 0, 0)
        area = round(0.5 * math.sqrt(sum(c * c for c in _face_normal(v3)))) if nv >= 3 else 0
        rows.append({"idx": idx, "facing": _poly_facing(v3) if nv >= 3 else "?",
                     "texture": poly.texture or "-", "flags": decode_flags(poly.flags),
                     "pan": poly.pan, "centroid": cen, "area": area, "nverts": nv})
    return rows


def format_polys(actor: Actor, name: str) -> str:
    """Render list_polys as an aligned text table (the precise index↔face reference). `pan`
    (the `brush poly pan --to`/`--by` target) prints as `U,V`, or `-` when unset."""
    rows = list_polys(actor)
    out = [f"{name}: {len(rows)} polys",
           f"{'idx':>3}  {'facing':<6} {'texture':<18} {'centroid':<24} {'area':>8}  "
           f"{'pan':<8} flags"]
    for r in rows:
        c = r["centroid"]
        pan = f"{r['pan'][0]},{r['pan'][1]}" if r["pan"] is not None else "-"
        out.append(f"{r['idx']:>3}  {r['facing']:<6} {r['texture']:<18} "
                   f"{f'({c[0]},{c[1]},{c[2]})':<24} {r['area']:>8}  {pan:<8} "
                   f"{','.join(r['flags'])}")
    return "\n".join(out)


def _coord_component(d) -> str:
    """A reported world coordinate: tolerance-snapped, then formatted by the one shared formatter.

    `clean` matters here because these are DERIVED coordinates — `list_vertices` runs the vertices
    through the actor transform, so a brush sitting exactly on Y=228 reads 227.999994 after a 180°
    yaw (UE1's GMath table gives sin = -8.742278e-08). Without the snap this verb and `actor bbox`
    print different numbers for the same corner."""
    from .emit import clean, fmt_coord   # local: emit imports model, query imports emit lazily elsewhere
    return fmt_coord(clean(d))


def list_vertices(actor: Actor) -> list[dict]:
    """Welded brush corners (world coords) with the poly indices that share each —
    the inspect side of vertex editing. A corner is identified by coordinate, not a
    name. Empty for non-brush actors."""
    from .rotation import actor_linear, actor_prepivot, local_offset
    from .vertex import weld_vertices

    if not actor.brush:
        return []
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    loc = tuple(c if isinstance(c, Decimal) else Decimal(str(c)) for c in loc)
    # Weld on LOCAL coords first (the transform is linear → coincident locals stay coincident), then
    # apply PrePivot + the full linear transform to each welded corner. R=None + zero PrePivot keeps
    # the exact Decimal corner unchanged.
    R = actor_linear(actor)
    prepivot = actor_prepivot(actor)
    rows: list[dict] = []
    for w in weld_vertices(actor.brush):
        rc = local_offset(R, prepivot, w.coord)
        world = tuple(loc[i] + rc[i] for i in range(3))
        rows.append({"coord": world, "polys": sorted({pi for pi, _ in w.refs}),
                     "nrefs": len(w.refs)})
    return rows


def format_vertices(actor: Actor, name: str) -> str:
    """Render list_vertices as an aligned table (coordinate is the identity used by
    `brush vertex move --at`)."""
    rows = list_vertices(actor)
    out = [f"{name}: {len(rows)} vertices",
           f"{'coord':<28} {'polys':<16} {'refs':>4}"]
    for r in rows:
        c = r["coord"]
        coord = f"({_coord_component(c[0])},{_coord_component(c[1])},{_coord_component(c[2])})"
        polys = ",".join(str(p) for p in r["polys"])
        out.append(f"{coord:<28} {polys:<16} {r['nrefs']:>4}")
    return "\n".join(out)


def _class_matches(query: str, stored: str) -> bool:
    """Case-insensitive class match: full-ref exact OR last-dot-component match.

    `query` is what the user typed; `stored` is the actor's cls field (always
    fully qualified `Package.Name` once the level is loaded/materialized).
    """
    q = query.casefold()
    s = stored.casefold()
    return s == q or s.rsplit(".", 1)[-1] == q


def _group_matches(groups: list[str], actor: Actor) -> bool:
    """Return True if the actor belongs to any of the requested groups.

    Reads the FIRST `Group` prop entry (first-match convention), splits on
    comma, strips each element, and compares case-insensitively.
    """
    stored_value: str | None = None
    for k, v in actor.props:
        if k.casefold() == "group":
            stored_value = v
            break
    if stored_value is None:
        return False
    members = {s.strip().casefold() for s in stored_value.split(",")}
    return any(g.casefold() in members for g in groups)


def _folder_matches(patterns: list[str], actor: Actor) -> bool:
    """True if the actor's folder matches ANY of the globstar `patterns` (OR within `--folder`).
    A groupless actor (`folder is None`) matches no pattern — select the ungrouped set with the
    separate `no_folder` param. Globstar semantics live in `folderlib` (spec §3)."""
    from . import folderlib
    return any(folderlib.matches(p, actor.folder) for p in patterns)


def _label_matches(patterns: list[str], actor: Actor) -> bool:
    """True if ANY of the actor's labels matches ANY of the flat `*`-glob `patterns` (OR-within
    `--label` AND OR-across-labels). An unlabelled actor matches no pattern — select the unlabelled
    set with the separate `no_label` param. Flat `*`-only matching lives in `labellib` (spec §5)."""
    from . import labellib
    return any(labellib.match_label(p, lbl) for p in patterns for lbl in actor.labels)


def list_actors(
    level: Level,
    *,
    name_glob: str | None = None,
    cls: str | None = None,
    names: list[str] | None = None,
    classes: list[str] | None = None,
    groups: list[str] | None = None,
    folders: list[str] | None = None,
    no_folder: bool = False,
    labels: list[str] | None = None,
    no_label: bool = False,
    kind: Literal["point", "brush"] | None = None,
) -> list[str]:
    """Return names of actors matching all supplied filters.

    Within each list-typed filter (names/classes/groups/folders) the match is OR
    (any value matches). Across different filters AND applies: the legacy
    singular name_glob/cls AND together with the new list filters.
    `kind` filters on whether the actor has a brush (brush is not None).
    `folders` is a list of globstar folder patterns (uedcli-side folder dimension,
    §3); `no_folder` selects only ungrouped actors (folder is None) and is
    mutually exclusive with `folders` at the CLI.
    `labels` is a list of flat `*`-glob label patterns (uedcli-side label dimension,
    §5): an actor passes if ANY of its labels matches ANY pattern; `no_label` selects
    only unlabelled actors (empty label set) and is mutually exclusive with `labels`
    at the CLI.
    (`--prop` matching moved OUT of this query to the dispatch find handler —
    it is EFFECTIVE-value matching over the class schema/defaults now, spec
    2026-07-18; this function stays schema-free.)

    Output order: actors present in `level.order` come first (in order), followed
    by any remainder in `level.actors` not covered by `level.order`. This makes
    ordering explicit and deterministic — never accidentally driven by dict insertion
    order, which would only coincide with `level.order` on well-formed levels.
    """
    def _passes(name: str, a: "Actor") -> bool:
        if name_glob and not fnmatch.fnmatch(name.lower(), name_glob.lower()):
            return False
        if cls and not _class_matches(cls, a.cls):
            return False
        if names is not None and not any(
            fnmatch.fnmatch(name.lower(), n.lower()) for n in names
        ):
            return False
        if classes is not None and not any(_class_matches(c, a.cls) for c in classes):
            return False
        if groups is not None and not _group_matches(groups, a):
            return False
        if folders is not None and not _folder_matches(folders, a):
            return False
        if no_folder and a.folder is not None:
            return False
        if labels is not None and not _label_matches(labels, a):
            return False
        if no_label and a.labels:
            return False
        if kind == "point" and a.brush is not None:
            return False
        if kind == "brush" and a.brush is None:
            return False
        return True

    out = []
    seen: set[str] = set()
    # Emit ordered actors first, then any in level.actors missing from level.order.
    for name in level.order:
        if name in level.actors:
            a = level.actors[name]
            seen.add(name)
            if _passes(name, a):
                out.append(name)
    for name, a in level.actors.items():
        if name not in seen and _passes(name, a):
            out.append(name)
    return out


def resolve_actor_name(level: Level, name: str) -> str:
    """Return the canonical stored name for `name`, case-insensitively.

    Fast path: exact match returns immediately. Otherwise folds case and scans
    `level.actors`; raises `KeyError(f"Actor not found: {name}")` on no match.
    Callers must access the message via `e.args[0]`, NOT `str(e)` — Python wraps
    `KeyError` messages in extra quotes when stringified.
    """
    if name in level.actors:
        return name
    fold = name.casefold()
    # No case-only collision possible: Unreal FName storage is case-insensitive, so two
    # stored names can't differ only in case.
    for stored in level.actors:
        if stored.casefold() == fold:
            return stored
    raise KeyError(f"Actor not found: {name}")


def _csg_oper(actor) -> str:
    """The brush's CSG operation string (`CSG_Add`/`CSG_Subtract`); `CSG_Add` if unset. Key match is
    case-insensitive (an imported map may spell the prop key differently than uedcli authors it)."""
    for k, v in actor.props:
        if k.casefold() == "csgoper":
            return v
    return "CSG_Add"
def resolve_actor_names(level: Level, names: Sequence[str]) -> list[str]:
    """Resolve every name in `names` to its canonical stored form, all-or-nothing.

    Collects every miss before raising so the error reports all bad names at once:
    `KeyError(f"Actors not found: {', '.join(missing)}")`. Returns canonical names
    in input order.
    """
    resolved: list[str] = []
    missing: list[str] = []
    for name in names:
        try:
            resolved.append(resolve_actor_name(level, name))
        except KeyError:
            missing.append(name)
    if missing:
        raise KeyError(f"Actors not found: {', '.join(missing)}")
    return resolved


def actor_show_block(actor: Actor, with_sidecars: bool) -> str:
    """The `actor show` block for one actor: canonical T3D, plus — when `with_sidecars` — the bare
    `// uedcli-folder: <path>` and `// uedcli-labels: a,b` carrier lines inside the block (spec §4,
    §6), each emitted only when the corresponding sidecar is set. The carriers make the DEFAULT
    output BOTH sidecar-round-tripping (`actor show A | actor add -` reads them back into the
    sidecars) AND UnrealEd-importable (the editor silently strips bare `//` lines). `--t3d-only`
    passes `with_sidecars=False` for a byte-exact editor export. The folder/labels live only in the
    sidecars — a stored trunk body never contains these lines; they are generated here from the
    fields."""
    from .emit import inject_carriers
    t = canonical_actor_t3d(actor)
    if not with_sidecars:
        return t
    return inject_carriers(t, actor)                       # shared seam (folder + labels carriers)


def show_actor(level: Level, name: str, *, with_sidecars: bool = False) -> str:
    """Return canonical T3D for the ONE actor called `name` (with the `// uedcli-folder:` /
    `// uedcli-labels:` carriers when `with_sidecars`).

    A **pure name resolver — it does NOT glob.** Matching is case-insensitive (FName semantics,
    via `resolve_actor_name`); a token naming no actor raises ``KeyError("Actor not found: …")``,
    which dispatch turns into that message on stderr and exit 2 — the house bad-actor-name rule,
    never a silent empty rc-0.

    Pattern matching lives in `actor find`, and `actor find <pattern> | actor show -` prints the
    whole matched set. `show` carrying a SECOND, redundant pattern mechanism contradicted the
    compose philosophy, and its zero-match glob printed a blank line at exit 0 (owner ruling,
    2026-07-25).
    """
    return actor_show_block(level.actors[resolve_actor_name(level, name)], with_sidecars)


def describe(level: Level) -> dict:
    """Return a summary dict: total actor count and count per class."""
    by_class = Counter(a.cls for a in level.actors.values())
    return {"total": len(level.actors), "by_class": dict(by_class)}


def level_bounds(level):
    """World AABB (x0,y0,z0,x1,y1,z1) over every actor's Location and brush WORLD vertices (honours
    the actor Rotation field via world_vertices — rotation is NOT vertex-baked). None for an empty
    level. Model-side; drives preview's camera jump."""
    from .rotation import world_vertices

    pts: list[tuple[float, float, float]] = []
    for a in level.actors.values():
        loc = a.location or (0, 0, 0)
        pts.append((float(loc[0]), float(loc[1]), float(loc[2])))
        pts.extend(world_vertices(a))          # honours actor Rotation (spec); empty for non-brush
    if not pts:
        return None
    xs, ys, zs = (sorted(p[i] for p in pts) for i in range(3))
    return (xs[0], ys[0], zs[0], xs[-1], ys[-1], zs[-1])


def level_center(level):
    b = level_bounds(level)
    if b is None:
        return None
    return ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)


def list_mover_keys(actor) -> list[dict]:
    """Structured form of `format_mover_keys` (the `--json` payload): one dict per key with `idx`,
    the absolute `world_pos`/`world_rot`, the stored `off_pos`/`off_rot`, and `base` (True for key
    0). Poses are plain int/float triples (world_pos is Decimal-derived → normalized to int when
    integral, matching the text table's rendering)."""
    from decimal import Decimal

    from . import movers, rotation
    base_pos = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    base_rot = rotation.actor_rotation_uu(actor)

    def trip(t):
        from .emit import num_coord
        return [num_coord(c) for c in t]

    rows: list[dict] = []
    for i, off_pos, off_rot in movers.mover_keys(actor):
        wpos = tuple(base_pos[j] + off_pos[j] for j in range(3))
        wrot = rotation.compose_uu(off_rot, base_rot)
        rows.append({"idx": i, "world_pos": trip(wpos), "world_rot": trip(wrot),
                     "off_pos": trip(off_pos), "off_rot": trip(off_rot), "base": i == 0})
    return rows


def format_mover_keys(actor) -> str:
    """Human/scriptable table of a mover's keys: idx, absolute world pose, and stored offset.
    world = base (Location/Rotation) + the key's offset; key 0 is the base (zero offset)."""
    from decimal import Decimal

    from . import movers, rotation
    base_pos = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    base_rot = rotation.actor_rotation_uu(actor)

    def trip(t):
        return ",".join(str(int(c) if Decimal(str(c)) == int(Decimal(str(c))) else c) for c in t)

    rows = ["idx world_pos world_rot off_pos off_rot"]
    for i, off_pos, off_rot in movers.mover_keys(actor):
        wpos = tuple(base_pos[j] + off_pos[j] for j in range(3))
        wrot = rotation.compose_uu(off_rot, base_rot)
        tag = " (base)" if i == 0 else ""
        rows.append(f"{i} {trip(wpos)} {trip(wrot)} {trip(off_pos)} {trip(off_rot)}{tag}")
    return "\n".join(rows)
