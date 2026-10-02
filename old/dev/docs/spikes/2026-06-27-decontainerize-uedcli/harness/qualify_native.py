"""Native (no-editor) replacement for the two qualification ops uedcli currently
does via the live editor:

  OBJ DEPENDENCIES PACKAGE=MyLevel  -> per-poly Texture package qualification
  OBJ LIST CLASS=Class              -> bare actor-class -> package qualification

Two cases:

A. READ-FROM-`.dx`: the map's OWN import table already names every external object
   fully qualified (package + class + object name). So `OBJ DEPENDENCIES` is just
   reading the import table we can already parse (`dxpkg`). No editor.

B. BUILD-FROM-SCRATCH / T3D (only bare names available): resolve a bare Texture/Class
   name against the level's manifest packages by enumerating their export tables and
   building a name -> {packages} index. Unique -> qualified; collision -> report all
   candidates (same contract the editor's approach has, but we can SEE every candidate).

Usage:
  python qualify_native.py imports <map.dx>
  python qualify_native.py index Texture <pkg> [<pkg> ...]   # build a name->pkg index
"""
from __future__ import annotations

import sys
from collections import defaultdict

sys.path.insert(0, ".")
from package_rw import Pkg


def _name(p, i):
    # package_rw keeps the raw name bytes (incl. trailing NUL) for byte-exact
    # re-encoding; strip the NUL for comparison/display.
    return p.names[i][0].split(b"\x00", 1)[0].decode("latin-1") if 0 <= i < len(p.names) else f"<{i}>"


def import_package(p, j):
    """Walk an import's PackageIndex chain to its root package name."""
    cur = p.imports[j]
    for _ in range(64):
        cp, cn, pi, on = cur
        if pi == 0:
            return _name(p, on)
        if pi < 0:
            cur = p.imports[-pi - 1]
        else:
            return None
    return None


def qualified_imports(path):
    """Every external object the package references, fully qualified, grouped by class.
    This IS what OBJ DEPENDENCIES recovers — straight from the import table."""
    p = Pkg(path)
    out = defaultdict(list)            # class-name -> ["Package.Object", ...]
    for j, (cp, cn, pi, on) in enumerate(p.imports):
        cls = _name(p, cn)
        obj = _name(p, on)
        if pi == 0:                    # this import IS a package (root); skip
            continue
        pkg = import_package(p, j)
        if pkg:
            out[cls].append(f"{pkg}.{obj}")
    return p, out


def build_index(klass, paths):
    """name(lower) -> set(package) over the export tables of the given packages."""
    idx = defaultdict(set)
    for path in paths:
        try:
            p = Pkg(path)
        except Exception:
            continue
        pkgname = path.split("/")[-1].rsplit(".", 1)[0]
        for cls, sup, outer, nm, fl, ssize, soff in p.exports:
            # class of an export = the export whose name is its 'cls' (local) or an import
            cref = cls
            cname = None
            if cref < 0:
                # export's class is an imported class object; its NAME is the
                # import's ObjectName (index 3), not its ClassName (index 1).
                cname = _name(p, p.imports[-cref - 1][3])
            elif cref > 0:
                cname = _name(p, p.exports[cref - 1][3])
            else:
                cname = "Class"
            if cname == klass:
                idx[_name(p, nm).lower()].add(pkgname)
    return idx


def main(argv):
    if argv[1] == "imports":
        p, out = qualified_imports(argv[2])
        print(f"{argv[2].split('/')[-1]} v{p.version}: {len(p.imports)} imports")
        for cls in ("Texture", "Class", "Mesh", "LodMesh", "Sound", "Music", "Palette"):
            refs = out.get(cls, [])
            if refs:
                print(f"  {cls}: {len(refs)} qualified  e.g. {refs[:4]}")
    elif argv[1] == "index":
        klass = argv[2]
        idx = build_index(klass, argv[3:])
        uniq = sum(1 for v in idx.values() if len(v) == 1)
        coll = {k: sorted(v) for k, v in idx.items() if len(v) > 1}
        print(f"{klass} index over {len(argv)-3} packages: {len(idx)} distinct names, "
              f"{uniq} unique, {len(coll)} collide")
        for k, v in list(coll.items())[:12]:
            print(f"  COLLISION {k}: {v}")


if __name__ == "__main__":
    main(sys.argv)
