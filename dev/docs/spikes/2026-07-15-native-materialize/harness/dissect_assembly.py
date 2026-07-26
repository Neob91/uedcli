"""Enumerate the FULL object set of a small real .dx: every export (class, name,
outer, flags, size) and every import (class, package, name), plus the ULevel Actors
array order. This grounds the 'minimal object set + import/name table' assembly spec.

Usage: python dissect_assembly.py <map.dx>
"""
from __future__ import annotations
import struct, sys
sys.path.insert(0,"/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness")
from utexture_decode import load_package, ci

RF = {0x02000000:"HasStack",0x00000001:"Transactional",0x00000004:"Public",
      0x00000008:"LoadForClient",0x00000010:"LoadForServer",0x00000020:"LoadForEdit",
      0x00040000:"TagExp",0x00010000:"NotForClient",0x00020000:"NotForServer",
      0x04000000:"Standalone"}

def flagstr(f):
    return "|".join(v for k,v in RF.items() if f&k) or "-"

def main(argv):
    p = load_package(argv[1])
    print(f"{argv[1].split('/')[-1]} v{p.version}: names={len(p.names)} imports={len(p.imports)} exports={len(p.exports)}")
    print("\n=== IMPORTS (idx: ObjName [Class] from Package  outer) ===")
    for j,(cp,cn,pi,on) in enumerate(p.imports):
        clsp = p.names[cp]; cls = p.names[cn]; obj = p.names[on]
        outer = p.name_of_ref(pi) if pi else "(root)"
        print(f"  imp[{j}] ref={-(j+1):<4} {obj:22s} [{clsp}.{cls}]  outer={outer}")
    print("\n=== EXPORTS (idx: Name [Class] outer flags size) ===")
    for i,e in enumerate(p.exports):
        cls = p.class_of_export(i) or "Class"
        nm = p.names[e['nm']]
        outer = p.name_of_ref(e['outer']) if e['outer'] else "(pkg root)"
        print(f"  exp[{i}] ref={i+1:<4} {nm:22s} [{cls:14s}] outer={outer!s:14s} "
              f"fl={flagstr(e['flags'])} size={e['ssize']}")

if __name__=="__main__":
    main(sys.argv)
