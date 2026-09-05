#!/usr/bin/env python3
"""Extract a built map's path-build INPUTS (`build_path_graph`'s arguments) as `cargo test` fixtures.

    extract_world.py <map.dx> <ued22|deusex> <out-prefix>

Writes `<out-prefix>.world.txt` (nav / zone / mover / level_zone lines, roster order),
`<out-prefix>.model.bin` (the `ULevel.Model` body) and `<out-prefix>.mover<k>.bin` (each Mover's
`Brush` model body).  Class kinds and collision sizes come from the engine's own `Engine.u`
(`uedcli.uprops.resolve_class_defaults`), never from a name guess.  Zone lines carry the
ZoneInfo's Location: the Rust test resolves the zone number with its own `PointRegion`.
"""
import glob
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-05-pathing-build-re/harness"))
from retail_stats import export_fqcn, is_nav_class, load_package, parse_level  # noqa: E402
from uedcli.upackage import read_compact_index, read_property_tags  # noqa: E402
from uedcli.uprops.uclass import _super_fqcn  # noqa: E402
from uedcli.uprops.values import resolve_class_defaults  # noqa: E402

RF_HasStack = 0x02000000
SYSTEMS = {"ued22": ROOT.parent.parent.parent / "uned/UED22", "deusex": ROOT.parent.parent.parent / "dev/games/deusex/System"}
KINDS = ("LiftCenter", "LiftExit", "Teleporter", "WarpZoneMarker", "PlayerStart")


def make_resolver(system: Path):
    def resolver(name: str) -> str | None:
        hits = [h for h in glob.glob(f"{system}/*.u") if h.split("/")[-1].casefold() == f"{name}.u".casefold()]
        return hits[0] if hits else None
    return resolver


def chain(pkg, fq: str, resolver) -> list[str]:
    out = []
    cur = fq
    for _ in range(40):
        if cur is None:
            break
        out.append(cur.split(".", 1)[1])
        pkg_name, cls = cur.split(".", 1)
        path = resolver(pkg_name)
        if path is None:
            break
        cur = _super_fqcn(load_package(path, name=pkg_name), cls)
    return out


def tags_of(pkg, i):
    e = pkg.exports[i]
    buf, pos, end = pkg.buf, e["soff"], e["soff"] + e["ssize"]
    if e["flags"] & RF_HasStack:
        node, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        pos += 12
        if node != 0:
            _, pos = read_compact_index(buf, pos)
    tags, _ = read_property_tags(pkg, pos, end)
    return {(t.name, t.array_index): t for t in tags}


def vec(tags, name, default=(0.0, 0.0, 0.0)):
    t = tags.get((name, 0))
    return struct.unpack("<fff", t.raw) if t else default


def rot(tags):
    t = tags.get(("Rotation", 0))
    return struct.unpack("<iii", t.raw) if t else (0, 0, 0)


def flt(tags, name, default):
    t = tags.get((name, 0))
    return struct.unpack("<f", t.raw)[0] if t else default


def boolean(tags, name, default):
    t = tags.get((name, 0))
    return t.bool_value if t else default


def name_of(pkg, tags, name):
    t = tags.get((name, 0))
    if not t:
        return "none"
    return pkg.names[read_compact_index(t.raw, 0)[0]].casefold()


def string_of(tags, name):
    t = tags.get((name, 0))
    if not t:
        return ""
    n, pos = read_compact_index(t.raw, 0)
    return t.raw[pos:pos + n - 1].decode("latin-1").casefold() if n > 0 else ""


def main(path: str, engine: str, out: str) -> None:
    resolver = make_resolver(SYSTEMS[engine])
    pkg = load_package(path)
    refs, _ = parse_level(pkg)
    li = next(i for i, e in enumerate(pkg.exports) if pkg.object_class_name(i + 1) == "Level")
    e = pkg.exports[li]
    buf, pos = pkg.buf, e["soff"]
    _, pos = read_property_tags(pkg, pos, e["soff"] + e["ssize"])
    num = struct.unpack_from("<i", buf, pos)[0]
    pos += 8
    for _ in range(num):
        _, pos = read_compact_index(buf, pos)
    for _ in range(4):
        n, pos = read_compact_index(buf, pos)
        pos += n if n >= 0 else -2 * n
    opc, pos = read_compact_index(buf, pos)
    for _ in range(opc):
        n, pos = read_compact_index(buf, pos)
        pos += n if n >= 0 else -2 * n
    pos += 8
    model_ref, pos = read_compact_index(buf, pos)
    me = pkg.exports[model_ref - 1]
    Path(f"{out}.model.bin").write_bytes(buf[me["soff"]:me["soff"] + me["ssize"]])
    lines = [f"# {Path(path).name} {engine}"]
    defaults_cache: dict[str, dict] = {}

    def defaults(fq):
        if fq not in defaults_cache:
            defaults_cache[fq] = resolve_class_defaults(fq, resolver=resolver)
        return defaults_cache[fq]

    n = 0
    movers = 0
    for r in refs:
        if r <= 0:
            continue
        fq = export_fqcn(pkg, r - 1)
        if fq.startswith("MyLevel."):
            continue
        ch = chain(pkg, fq, resolver)
        tags = tags_of(pkg, r - 1)
        d = defaults(fq)
        if is_nav_class(fq):
            kind = next((k for k in KINDS if k in ch), "NavigationPoint").casefold()
            x, y, z = vec(tags, "Location")
            p, yw, rl = rot(tags)
            cr = flt(tags, "CollisionRadius", float(d.get(("collisionradius", 0), 0)))
            chh = flt(tags, "CollisionHeight", float(d.get(("collisionheight", 0), 0)))
            one = int(boolean(tags, "bOneWayPath", False))
            lines.append(f"nav {n} {pkg.names[pkg.exports[r - 1]['nm']]} {kind} {x!r} {y!r} {z!r} {p} {yw} {rl} {cr!r} {chh!r} {one} "
                         f"{name_of(pkg, tags, 'LiftTag')} {string_of(tags, 'URL') or 'none'} {name_of(pkg, tags, 'Tag')}")
            n += 1
        elif "ZoneInfo" in ch and "LevelInfo" not in ch:
            x, y, z = vec(tags, "Location")
            g = vec(tags, "ZoneGravity", (0.0, 0.0, -950.0))
            v = vec(tags, "ZoneVelocity")
            lines.append(f"zone {x!r} {y!r} {z!r} {int(boolean(tags, 'bWaterZone', False))} {int(boolean(tags, 'bPainZone', False))} "
                         f"{name_of(pkg, tags, 'DamageType')} {g[0]!r} {g[1]!r} {g[2]!r} {flt(tags, 'ZoneFluidFriction', 1.2)!r} {v[0]!r} {v[1]!r} {v[2]!r}")
        elif "LevelInfo" in ch:
            g = vec(tags, "ZoneGravity", (0.0, 0.0, -950.0))
            v = vec(tags, "ZoneVelocity")
            lines.append(f"level_zone {int(boolean(tags, 'bWaterZone', False))} {int(boolean(tags, 'bPainZone', False))} "
                         f"{name_of(pkg, tags, 'DamageType')} {g[0]!r} {g[1]!r} {g[2]!r} {flt(tags, 'ZoneFluidFriction', 1.2)!r} {v[0]!r} {v[1]!r} {v[2]!r}")
        elif "Mover" in ch:
            bt = tags[("Brush", 0)]
            bref = read_compact_index(bt.raw, 0)[0]
            be = pkg.exports[bref - 1]
            Path(f"{out}.mover{movers}.bin").write_bytes(buf[be["soff"]:be["soff"] + be["ssize"]])
            x, y, z = vec(tags, "Location")
            p, yw, rl = rot(tags)
            px, py, pz = vec(tags, "PrePivot")
            block = int(boolean(tags, "bBlockActors", d.get(("bblockactors", 0), "True") == "True"))
            lines.append(f"mover {movers} {pkg.names[pkg.exports[r - 1]['nm']]} {x!r} {y!r} {z!r} {p} {yw} {rl} {px!r} {py!r} {pz!r} {block}")
            movers += 1
    Path(f"{out}.world.txt").write_text("\n".join(lines) + "\n")
    print(f"{out}: {n} navs, {movers} movers, model {me['ssize']} bytes", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:4])
