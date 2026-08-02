"""The INVARIANT's teeth (dev/docs/direction/trunk-and-editor.md 2026-07-18 23:01 UTC): the trunk, a stash, and a prefab MUST
be the SAME on-disk per-actor T3D tree, written through ONE shared code path. This test writes ONE
fixed actor set three ways and asserts the three `actors/` subtrees are BYTE-IDENTICAL — a violation
(a divergent writer creeping back in) trips a red test.
"""
from decimal import Decimal

from uedcli import trunk, stash_register, stashlib, t3dtree
from uedcli.model import Actor, Brush, Level, Polygon
from uedcli.normalize import canonical_actor_t3d


def _brush_actor(name):
    poly = Polygon(texture="DeusExDeco.Stone.Block", vertices=[
        (Decimal(0), Decimal(0), Decimal(0)),
        (Decimal(64), Decimal(0), Decimal(0)),
        (Decimal(64), Decimal(64), Decimal(0)),
    ])
    return Actor(name=name, cls="Engine.Brush",
                 brush=Brush(model_name=f"Model_{name}", polys=[poly]),
                 props=[("CsgOper", "CSG_Add")])


def _point_actor(name):
    return Actor(name=name, cls="Engine.Light", location=(Decimal(10), Decimal(20), Decimal(30)))


def _read_tree_bytes(actors_dir):
    """Every file under `actors/` → {relpath: bytes}."""
    out = {}
    for p in sorted(actors_dir.rglob("*")):
        if p.is_file():
            out[p.relative_to(actors_dir).as_posix()] = p.read_bytes()
    return out


def test_trunk_stash_prefab_write_byte_identical_actor_trees(tmp_path):
    # A fixed, FOLDER-LESS actor set (§4: a folder-less set is the one a folderless-blob wrapper can
    # reproduce byte-for-byte across all three trees).
    names = ["Arch", "Lamp"]
    actors = {"Arch": _brush_actor("Arch"), "Lamp": _point_actor("Lamp")}
    order = names

    # --- trunk arm: seed ranks with initial_ranks over the SAME order the wrappers derive ---
    level = Level(actors=dict(actors), order=list(order))
    ranks = dict(zip(order, t3dtree.initial_ranks(len(order))))
    trunk_dir = tmp_path / "trunk"
    trunk.write_level(trunk_dir, level, ranks)

    # --- stash arm & prefab arm: hand the SAME actors as canonical blobs ---
    full = {n: canonical_actor_t3d(actors[n]) for n in order}
    reg = stash_register.FileStashRegister(tmp_path / "stash_root")
    reg.write_stash("s", full_level=full, order=order, packages=["DeusExDeco"],
                    meta={"anchor": ["0", "0", "0"], "ts": 1})
    stash_dir = reg.root / "s"

    stashlib.write_prefab(tmp_path / "prefabs", "p", full_level=full, order=order,
                          packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    prefab_dir = tmp_path / "prefabs" / "p"

    trunk_tree = _read_tree_bytes(trunk_dir / "actors")
    stash_tree = _read_tree_bytes(stash_dir / "actors")
    prefab_tree = _read_tree_bytes(prefab_dir / "actors")

    # THE INVARIANT: every actor.t3d and order_value is byte-identical across all three trees.
    assert trunk_tree == stash_tree, "stash actors/ tree diverges from the trunk"
    assert trunk_tree == prefab_tree, "prefab actors/ tree diverges from the trunk"
    # No folder file anywhere (the set is folder-less).
    assert not any(k.endswith("/folder") for k in trunk_tree)

    # The stash/prefab EXTRAS sit BESIDE actors/ (never inside it), and the trunk has none.
    assert (stash_dir / "meta.json").is_file() and (stash_dir / "packages").is_file()
    assert (prefab_dir / "meta.json").is_file() and (prefab_dir / "packages").is_file()
    assert not (trunk_dir / "meta.json").exists() and not (trunk_dir / "packages").exists()
