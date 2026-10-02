"""Print the editor-bool declaration run from Engine.Actor's own stored ScriptText."""
import sys, re
sys.path.insert(0, ".")
from uedcli.uprops import load_package
from uedcli.uprops.uclass import _class_script_source

pkg = load_package("uned/UED22/Engine.u")
src = _class_script_source(pkg, "Actor")
if not src:
    print("no ScriptText")
    raise SystemExit(1)
lines = src.splitlines()
for i, ln in enumerate(lines):
    if re.search(r"\bbSelected\b|\bbEdShouldSnap\b|\bbEdLocked\b|\bbHiddenEd\b|\bbMemorized\b|\bbHighlighted\b|\bbDirectional\b|\bbEdSnap\b", ln):
        print(f"{i:5} {ln.strip()}")
