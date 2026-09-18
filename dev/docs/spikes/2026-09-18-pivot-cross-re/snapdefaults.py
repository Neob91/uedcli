"""Which classes in uned/UED22's packages set bEdShouldSnap=True in their class defaults?"""
import sys, pathlib
sys.path.insert(0, ".")
from uedcli.uprops import load_package, iter_classes, class_default_tags

hits = []
for p in sorted(pathlib.Path("uned/UED22").glob("*.u")):
    try:
        pkg = load_package(str(p))
    except Exception as e:  # noqa: BLE001
        print("skip", p.name, e)
        continue
    for cls in iter_classes(pkg):
        name = cls if isinstance(cls, str) else getattr(cls, "name", str(cls))
        try:
            tags = class_default_tags(pkg, name)
        except Exception:  # noqa: BLE001
            continue
        for t in tags:
            if str(getattr(t, "name", "")).lower() == "bedshouldsnap":
                hits.append((p.name, name, getattr(t, "bool_value", None)))
for h in hits:
    print(h)
print("total", len(hits))
