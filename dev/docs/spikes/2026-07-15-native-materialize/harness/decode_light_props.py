"""Decode the property tags of every Light export in a .dx, skipping the StateFrame
(RF_HasStack actors carry one before the tagged-property list).  Prints each light's
props so we can diff a real DeusEx light vs our synthesized Light0 — hunting a missing
LIFETIME prop (bStatic/bNoDelete/bMovable/bStaticLighting) that would let the engine
destroy the light after load and leave Model.Lights dangling."""
import sys, struct
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness")
from utexture_decode import load_package, ci, read_props

RF_HasStack = 0x02000000


def skip_stateframe(buf, pos):
    node, pos = ci(buf, pos)
    stnode, pos = ci(buf, pos)
    pos += 8   # ProbeMask u64
    pos += 4   # LatentAction u32
    if node != 0:
        _off, pos = ci(buf, pos)   # Offset (present when Node != 0)
    return pos


def decode(path):
    print(f"\n===== {path.split('/')[-1]} =====")
    p = load_package(path)
    lights = [i for i, e in enumerate(p.exports) if (p.class_of_export(i) or "").endswith("Light")]
    # include DeusEx light subclasses too
    for i, e in enumerate(p.exports):
        c = p.class_of_export(i) or ""
        if "Light" in c and i not in lights:
            lights.append(i)
    for i in sorted(set(lights)):
        e = p.exports[i]
        nm = p.names[e["nm"]]
        cls = p.class_of_export(i)
        flags = e["flags"]
        pos = e["soff"]
        if flags & RF_HasStack:
            pos = skip_stateframe(p.buf, pos)
        end = e["soff"] + e["ssize"]
        props, _ = read_props(p.buf, pos, end, p.names)
        print(f"  [{i}] {cls} {nm} flags=0x{flags:08x} ssize={e['ssize']}")
        for k in sorted(props):
            print(f"        {k} = {props[k]}")


for path in sys.argv[1:]:
    decode(path)
