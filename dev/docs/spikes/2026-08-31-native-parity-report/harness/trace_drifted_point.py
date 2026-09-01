#!/usr/bin/env python3
"""For a given native Points[] index, find which surf(s)/node(s) reference it (via p_base or the
node's own vert pool -> BspVert.i_vertex) and which brush ACTOR each surf's i_actor traces back to.
One-off diagnostic, NYC Bar point-value-drift investigation.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import parity_compare as pc  # noqa: E402

TRUNK = Path(sys.argv[1])
GOLDEN = Path(sys.argv[2])
TARGET_IDX = int(sys.argv[3])

native_model, level = pc.build_native_model(TRUNK)
print(f"target native point[{TARGET_IDX}] = {native_model.points[TARGET_IDX]!r}")

# surfs whose p_base is the target
p_base_hits = [i for i, s in enumerate(native_model.surfs) if s.p_base == TARGET_IDX]
print(f"\nsurfs with p_base == {TARGET_IDX}: {p_base_hits}")

# nodes -> vert pool -> BspVert.i_vertex == target; map back to node's i_surf
vert_hits = []
for ni, node in enumerate(native_model.nodes):
    for k in range(node.num_vertices):
        vidx = node.i_vert_pool + k
        if vidx < len(native_model.verts) and native_model.verts[vidx].i_vertex == TARGET_IDX:
            vert_hits.append((ni, node.i_surf, k))
print(f"\nnode vert-pool hits (node_idx, i_surf, slot): {vert_hits[:20]} ({len(vert_hits)} total)")

surf_idxs = sorted(set(p_base_hits) | {s for _, s, _ in vert_hits})
print(f"\nall touching surfs: {surf_idxs}")

# brush actor per surf: i_actor is a transient CSG-brush-list index in the bare build_geometry_bspcsg
# output (per parity_compare.compare_content's docstring) -- resolve via the level's own brush order.
import uedcli_native  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
from spike_classindex import class_index  # noqa: E402

ci = class_index()
names = [n for n in level.order
         if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
for si in surf_idxs:
    s = native_model.surfs[si]
    actor_name = names[s.i_actor] if 0 <= s.i_actor < len(names) else f"<oob {s.i_actor}>"
    print(f"  surf[{si}]: i_actor={s.i_actor} -> actor={actor_name!r}, "
          f"texture_ref={s.texture_ref}, poly_flags={s.poly_flags:#x}, "
          f"v_normal={s.v_normal} normal={native_model.vectors[s.v_normal]!r}")
