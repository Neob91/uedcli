"""How often does a real built node's plane point OPPOSITE its surf's vNormal (a 'flipped' node)?"""
import sys
sys.path.insert(0, '.')
from uedcli.bsp.builtmodel import load_model_from_dx

for path in sys.argv[1:]:
    m = load_model_from_dx(open(path, 'rb').read())
    same = opp = 0
    for n in m.nodes:
        if n.i_surf < 0:
            continue
        s = m.surfs[n.i_surf]
        v = m.vectors[s.v_normal]
        d = n.plane[0] * v[0] + n.plane[1] * v[1] + n.plane[2] * v[2]
        if d >= 0:
            same += 1
        else:
            opp += 1
    print(f"{path}: nodes with plane.vNormal >= 0: {same}, flipped (< 0): {opp}")
