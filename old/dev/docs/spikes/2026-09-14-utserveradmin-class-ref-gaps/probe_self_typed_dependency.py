import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("UEDCLI_HOME", os.path.abspath("_scratch/uedcli-home"))
state_dir = os.path.abspath("_scratch/state_selfdep")
os.makedirs(state_dir, exist_ok=True)

from uedcli.uscript.reference import ucc_compile, ucc_container

SOURCES = {
    "SelfDepNode.uc": (
        "class SelfDepNode expands Object;\n"
        "var SelfDepNode Next;\n"
        "var int Tag;\n"
        "function int SumNext(SelfDepNode Start)\n{\n"
        "    local SelfDepNode T;\n"
        "    local int Total;\n"
        "    for (T = Start; T != None; T = T.Next)\n"
        "        Total += T.Tag;\n"
        "    return Total;\n}\n"
    ),
}

with ucc_container(state_dir=state_dir) as c:
    u = ucc_compile(c, "SelfDepProbe", SOURCES)

out_path = os.path.abspath("_scratch/SelfDepProbe.u")
with open(out_path, "wb") as f:
    f.write(u)
print("compiled", len(u), "bytes")
