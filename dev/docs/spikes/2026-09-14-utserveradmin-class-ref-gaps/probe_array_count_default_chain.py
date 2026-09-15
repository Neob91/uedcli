import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("UEDCLI_HOME", os.path.abspath("_scratch/uedcli-home"))
state_dir = os.path.abspath("_scratch/state_acprobe2")
os.makedirs(state_dir, exist_ok=True)

from uedcli.uscript.reference import ucc_compile, ucc_container
from uedcli.uscript.natives import read_function
from uedcli.upackage import load_package

SOURCES = {
    "AC2Base.uc": (
        "class AC2Base expands Object;\n"
        "var string Maps[6];\n"
        "defaultproperties\n{\n}\n"
    ),
    "AC2Sub.uc": (
        "class AC2Sub expands Object;\n"
        "var class<AC2Base> MapListType;\n"
    ),
    "AC2User.uc": (
        "class AC2User expands Object;\n"
        "function int ViaDefault(Object O)\n{\n"
        "    local class<AC2Base> C;\n"
        "    C = class<AC2Base>(O);\n"
        "    return ArrayCount(C.Default.Maps);\n}\n"
        "function int ViaNested(Object O)\n{\n"
        "    local class<AC2Sub> S;\n"
        "    S = class<AC2Sub>(O);\n"
        "    return ArrayCount(S.Default.MapListType.Default.Maps);\n}\n"
    ),
}

with ucc_container(state_dir=state_dir) as c:
    u = ucc_compile(c, "AC2Probe", SOURCES)

out_path = os.path.abspath("_scratch/AC2Probe.u")
with open(out_path, "wb") as f:
    f.write(u)
print("compiled", len(u), "bytes")

pkg = load_package(out_path)
for i, e in enumerate(pkg.exports):
    cls = pkg.name_of_ref(e["cls"])
    nm = pkg.names[e["nm"]] if 0 <= e["nm"] < len(pkg.names) else "?"
    if cls == "Function":
        fb = read_function(pkg, i + 1)
        print(f"\n== function {nm} ==")
        for t in fb.tokens:
            print(" ", t)
