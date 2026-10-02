"""Decode Editor.EditorEngine's own script property list (declaration order) from our own
uned/UED22/Editor.u, then lay it out the way UE1's UStruct::Link does, and check the layout
against offsets already read out of Editor.dll's disassembly (Level=+0xa8, Mode=+0x118).
"""
import sys
sys.path.insert(0, ".")
from uedcli.uprops import load_package, own_class_properties

pkg = load_package("uned/UED22/Editor.u")
props = own_class_properties(pkg, "EditorEngine", owner_fqcn="Editor.EditorEngine")
for i, p in enumerate(props):
    print(f"{i:3}  {p.name:<28} {p.kind:<16} dim={p.array_dim}")
