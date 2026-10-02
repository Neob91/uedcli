import sys, struct
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
from uedcli.native.pkg_write import parse_package
from uedcli.native import umodel as UM
from uedcli.native.codec import read_ci

def load(path):
    buf = open(path, "rb").read()
    p = parse_package(buf)
    mi = [i for i in range(len(p.exports)) if p.class_of_export(i) == "Model"]
    mi.sort(key=lambda i: p.exports[i]["ssize"], reverse=True)
    i = mi[0]
    e = p.exports[i]
    return p.buf, e["soff"], e["ssize"]

def hexb(b):
    return " ".join(f"{x:02x}" for x in b)

def ci(data, pos):
    v, npos = read_ci(data, pos)
    return v, npos, data[pos:npos]

def dump_node0(tag, path):
    buf, soff, ssize = load(path)
    data = buf[soff:soff+ssize]
    print(f"\n===== {tag}  body size={ssize} =====")
    pos = 42  # PREFIX
    # vectors
    n, pos = read_ci(data, pos)
    pos += n*12
    # points
    n, pos = read_ci(data, pos)
    pos += n*12
    # nodes count
    ncount, pos = read_ci(data, pos)
    node0_start = pos
    print(f"nodes count={ncount}, node[0] starts at body offset {node0_start}")
    print(f"raw node[0..1] bytes ({64} shown):")
    print(hexb(data[node0_start:node0_start+64]))
    # hand decode node0
    p = node0_start
    plane = struct.unpack_from("<ffff", data, p); p0=p; p+=16
    print(f"  [+{p0-node0_start:02d}] Plane f32x4 = {plane}  raw={hexb(data[p0:p0+16])}")
    zmask = struct.unpack_from("<Q", data, p)[0]; p0=p; p+=8
    print(f"  [+{p0-node0_start:02d}] ZoneMask u64 = {zmask:#x}  raw={hexb(data[p0:p0+8])}")
    fb = data[p]; p0=p; p+=1
    print(f"  [+{p0-node0_start:02d}] byte = {fb:#x}")
    labels = ["iVertPool","iSurf","childA","childB","iPlane","F9","F10","F11","F12","NumVerts?"]
    for lab in labels:
        v, p, raw = ci(data, p)
        print(f"  [+{p-len(raw)-node0_start:02d}] ci {lab:10s} = {v}  raw={hexb(raw)}")
    # two i32
    for lab in ["Ti32_a","Ti32_b"]:
        v = struct.unpack_from("<i", data, p)[0]; p0=p; p+=4
        print(f"  [+{p0-node0_start:02d}] i32 {lab:8s} = {v}  raw={hexb(data[p0:p0+4])}")
    print(f"  node[0] total size = {p-node0_start} bytes; node[1] starts at {p}")
    return buf, soff, ssize, data

for tag, path in [("DXOnly", "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/DXOnly.dx"),
                  ("NativeCSG", "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCSG.dx")]:
    dump_node0(tag, path)
