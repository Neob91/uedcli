import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("UEDCLI_HOME", os.path.abspath("_scratch/uedcli-home"))
state_dir = os.path.abspath("_scratch/state_ncprobe")
os.makedirs(state_dir, exist_ok=True)

from uedcli.uscript.reference_ut99 import ucc_compile_ut99, ut99_container

SOURCES = {
    "NCProbe.uc": (
        "class NCProbe expands Object;\n"
        "function bool Check(Object O)\n{\n"
        "    return NetConnection(O) != None;\n}\n"
    ),
}

with ut99_container(state_dir=state_dir) as c:
    u = ucc_compile_ut99(c, "NCProbe", SOURCES)
print("compiled OK", len(u), "bytes")

out_path = os.path.abspath("_scratch/NCProbe.u")
with open(out_path, "wb") as f:
    f.write(u)

from uedcli.upackage import load_package
pkg = load_package(out_path)
for i, imp in enumerate(pkg.imports):
    cls_pkg = pkg.names[imp[0]] if 0 <= imp[0] < len(pkg.names) else "?"
    cls_name = pkg.names[imp[1]] if 0 <= imp[1] < len(pkg.names) else "?"
    obj_name = pkg.names[imp[3]] if 0 <= imp[3] < len(pkg.names) else "?"
    print(i + 1, "outer=", imp[2], "class=", f"{cls_pkg}.{cls_name}", "name=", obj_name)

