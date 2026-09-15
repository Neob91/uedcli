import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("UEDCLI_HOME", os.path.abspath("_scratch/uedcli-home"))
state_dir = os.path.abspath("_scratch/state_acprobe")
os.makedirs(state_dir, exist_ok=True)

from uedcli.uscript.reference import ucc_compile, ucc_container
from uedcli.uscript.natives import read_function
from uedcli.upackage import load_package

SOURCES = {
    "ACBase.uc": (
        "class ACBase expands Object;\n"
        "var string Maps[8];\n"
        "var int Small[3];\n"
    ),
    "ACUser.uc": (
        "class ACUser expands Object;\n"
        "function int ViaMember(ACBase B)\n{\n"
        "    return ArrayCount(B.Maps);\n}\n"
        "function int ViaSmall(ACBase B)\n{\n"
        "    return ArrayCount(B.Small);\n}\n"
    ),
}

with ucc_container(state_dir=state_dir) as c:
    u = ucc_compile(c, "ACProbe", SOURCES)

out_path = os.path.abspath("_scratch/ACProbe.u")
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
