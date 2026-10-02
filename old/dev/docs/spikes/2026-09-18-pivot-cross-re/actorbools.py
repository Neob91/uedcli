"""Inspect Engine.Actor's editor bool properties and Brush/Light defaults, from our own
uned/UED22 packages."""
import sys
sys.path.insert(0, ".")
from uedcli.uprops import load_package, own_class_properties, class_default_tags

pkg = load_package("uned/UED22/Engine.u")
props = own_class_properties(pkg, "Actor", owner_fqcn="Engine.Actor")
want = {"bedsnap", "bedshouldsnap", "bedlocked", "bselected", "bhiddened", "bnodelete"}
for p in props:
    if p.name.lower() in want:
        print(p)
print()
for cls in ("Brush", "Light", "Mover"):
    tags = class_default_tags(pkg, cls)
    for t in tags:
        nm = getattr(t, "name", str(t))
        if "snap" in str(nm).lower() or "Locked" in str(nm):
            print(cls, t)
