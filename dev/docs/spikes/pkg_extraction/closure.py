"""Transitive package closure for a .dx, offline, from package headers.

Direct deps come from the level's import table. Code packages (.u) carry
their own import tables, so we recurse into any dependency whose file we can
find and parse. Content packages (.utx/.uax/.umx) also have headers, but in a
stripped substrate their files are absent -> they're leaves we can't expand
(and that's exactly what the substrate must be made to ship).
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import dxpkg

# Where package files might live, in priority order (the substrate's path set).
SEARCH_DIRS = [
    "/home/human/src/dx_lum/Tools/uedctl/uned/UED22",
    "/home/human/src/dx_lum/Maps",
    "/home/human/src/dx_lum/Textures",
    "/home/human/src/dx_lum/System",
]
EXTS = [".u", ".dx", ".utx", ".uax", ".umx"]

def find_package_file(pkg):
    # Case-insensitive: the engine's package path resolves on Wine/NTFS, where
    # `core.u` satisfies a `Core` import.
    want = {(pkg + ext).lower() for ext in EXTS}
    for d in SEARCH_DIRS:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            if name.lower() in want:
                return os.path.join(d, name)
    return None

def closure(dx_path):
    seen = set()
    missing_files = set()
    frontier = [dx_path]
    # seed with the level itself; record its name as the root (excluded from deps)
    root_done = False
    while frontier:
        path = frontier.pop()
        try:
            ver, names, imports = dxpkg.parse(path)
        except Exception as e:
            continue
        deps = dxpkg.resolve_packages(names, imports)
        for pkg in deps:
            if pkg in seen:
                continue
            seen.add(pkg)
            f = find_package_file(pkg)
            if f is None:
                missing_files.add(pkg)
            elif f.lower().endswith(".u"):
                frontier.append(f)  # only code packages have expandable imports we care to recurse
    return seen, missing_files

if __name__ == "__main__":
    dx = sys.argv[1]
    deps, missing = closure(dx)
    print("== %s ==" % dx)
    print("transitive package closure (%d):" % len(deps))
    print("  " + ", ".join(sorted(deps)))
    print("MISSING from substrate path (%d):" % len(missing))
    print("  " + ", ".join(sorted(missing)))
