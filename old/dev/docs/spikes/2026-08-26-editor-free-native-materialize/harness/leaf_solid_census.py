#!/usr/bin/env python3
"""Census a built `.dx`'s world Model for solid-marked node slots and in-solid point actors.

The two checks the `native-bsp-leaf-assignment-marks-2x-the-solid` board item leaves behind:

  1. the whole-model `iLeaf == -1` (solid) node-slot count, and
  2. how many of the trunk's point actors `PointRegion`-resolve into zone 0 (solid), per class.

Run it on a natively built `.dx` and on the editor's own build of the same trunk; the numbers are
directly comparable because both carry the same node array shape.

    dev/docs/spikes/2026-08-26-editor-free-native-materialize/harness/leaf_solid_census.py \
        <trunk-actors-dir> <built.dx> [<built.dx> ...]

`<trunk-actors-dir>` is the project's `maps/<level>/actors/`, read only for each actor's `Location`
and `Class`. With two or more maps it also prints a per-node solid/empty diff of each against the
first — the check an aggregate count cannot make, since a front/back inversion moves solid slots
between a node's two sides without changing the total.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5]))

from uedcli.native import umodel  # noqa: E402
from uedcli.native.csg_golden import _find_model_export  # noqa: E402
from uedcli.native.materialize import _model_point_zone  # noqa: E402

_LOC = re.compile(r"^\s*Location=\(([^)]*)\)", re.M)
_CLS = re.compile(r"^Begin Actor Class=(\S+)", re.M)


def actor_locations(actors_dir: pathlib.Path) -> list[tuple[str, str, tuple]]:
    """`(name, short class, (x, y, z))` for every actor in the trunk that has a Location.

    An actor with no `Location` is skipped (it has no point to resolve); one whose `Location` or
    `Class` will not parse is fatal, so a silently shrinking denominator can never be quoted as a
    result.
    """
    out = []
    for d in sorted(actors_dir.iterdir()):
        t3d = d / "actor.t3d"
        if not t3d.is_file():
            continue
        text = t3d.read_text(errors="replace")
        if not (mloc := _LOC.search(text)):
            continue
        if not (mcls := _CLS.search(text)):
            raise SystemExit(f"{t3d}: has a Location but no parseable 'Begin Actor Class='")
        axes = dict(
            part.split("=", 1) for part in mloc.group(1).split(",") if "=" in part
        )
        try:  # an OMITTED axis is 0 in T3D; a present-but-unparseable one is an error
            loc = tuple(float(axes.get(a, "0")) for a in "XYZ")
        except ValueError as e:
            raise SystemExit(f"{t3d}: unparseable Location=({mloc.group(1)}): {e}") from e
        out.append((d.name, mcls.group(1).split(".")[-1], loc))
    return out


def report(dx: pathlib.Path, actors: list[tuple[str, str, tuple]]) -> None:
    model = load(dx)
    solid = sum(1 for n in model.nodes for s in (0, 1) if n.i_leaf[s] == -1)
    zone00 = sum(1 for n in model.nodes if n.i_zone[0] == 0 and n.i_zone[1] == 0)
    print(f"== {dx}")
    print(
        f"   nodes={len(model.nodes)} leaves={len(model.leaves)} zones={len(model.zones)} "
        f"surfs={len(model.surfs)}"
    )
    print(
        f"   iLeaf==-1 slots={solid}/{2 * len(model.nodes)}  "
        f"nodes with iZone==(0,0)={zone00}"
    )
    per_class = collections.Counter()
    total = collections.Counter()
    for _name, cls, loc in actors:
        total[cls] += 1
        if _model_point_zone(model, loc) == 0:
            per_class[cls] += 1
    print(f"   point actors in zone 0 (solid): {sum(per_class.values())}/{sum(total.values())}")
    for cls, n in per_class.most_common(12):
        print(f"     {cls:24s} {n:5d}/{total[cls]}")


def load(dx: pathlib.Path):
    raw = dx.read_bytes()
    return umodel.parse_model_body(raw, *_find_model_export(raw))


def per_node_diff(a: pathlib.Path, b: pathlib.Path) -> None:
    """Per-node solid/empty agreement, matched by PLANE rather than by array index.

    The aggregate `iLeaf == -1` count cannot see a front/back inversion: that moves solid slots
    between a node's two sides and leaves the total unchanged. This can. Nodes are paired by their
    plane (only planes unique within BOTH models, so the pairing is unambiguous) rather than by
    index, because two editor builds of one trunk need not lay the node array out in the same order.
    A systematic inversion shows up as a large "exactly swapped" count.
    """
    ma, mb = load(a), load(b)
    key = lambda pl: tuple(round(c, 3) for c in pl)  # noqa: E731
    uniq = []
    for m in (ma, mb):
        seen = collections.Counter(key(n.plane) for n in m.nodes)
        uniq.append({key(n.plane): n for n in m.nodes if seen[key(n.plane)] == 1})
    paired = swapped = differ = 0
    for pl, na in uniq[0].items():
        nb = uniq[1].get(pl)
        if nb is None:
            continue
        paired += 1
        solid_a = [na.i_leaf[s] == -1 for s in (0, 1)]
        solid_b = [nb.i_leaf[s] == -1 for s in (0, 1)]
        if solid_a == solid_b:
            continue
        differ += 1
        if solid_a == solid_b[::-1]:
            swapped += 1
    print(f"== per-node solid/empty diff, {a.name} vs {b.name}")
    print(
        f"   nodes paired by unique plane={paired}  differing solidity pattern={differ}  "
        f"of those, exactly swapped={swapped}"
    )


def main() -> None:
    args = sys.argv[1:]
    actors = actor_locations(pathlib.Path(args[0]))
    print(f"trunk actors with a Location: {len(actors)}")
    maps = [pathlib.Path(p) for p in args[1:]]
    for dx in maps:
        report(dx, actors)
    for other in maps[1:]:
        per_node_diff(maps[0], other)


main()
