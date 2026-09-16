import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("UEDCLI_HOME", os.path.abspath("_scratch/uedcli-home"))
state_dir = os.path.abspath("_scratch/state_scprobe")
os.makedirs(state_dir, exist_ok=True)

from uedcli.uscript.reference import ucc_compile, ucc_container
from uedcli.uscript.natives import read_function
from uedcli.upackage import load_package

SOURCES = {
    "SCBase.uc": (
        "class SCBase expands Object;\n"
        "var int Num;\n"
        "static function int GetNum()\n{\n    return 5;\n}\n"
        "function int GetNumInst()\n{\n    return 6;\n}\n"
    ),
    "SCUser.uc": (
        "class SCUser expands Object;\n"
        "function int ViaClassStatic(Object O)\n{\n"
        "    local class<SCBase> C;\n"
        "    C = class<SCBase>(O);\n"
        "    return C.Static.GetNum();\n}\n"
        "function CallVoid(Object O)\n{\n"
        "    local class<SCBase> C;\n"
        "    C = class<SCBase>(O);\n"
        "    C.Static.GetNum();\n}\n"
    ),
}

with ucc_container(state_dir=state_dir) as c:
    u = ucc_compile(c, "SCProbe", SOURCES)

out_path = os.path.abspath("_scratch/SCProbe.u")
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
