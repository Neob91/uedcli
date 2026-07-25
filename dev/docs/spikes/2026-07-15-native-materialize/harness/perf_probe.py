"""Workload counts for perf estimation: parse a real built map's Model + lightmap arrays.
Run:  python3.12 perf_probe.py   (needs no deps; parsers are stdlib)."""
import sys, math, os
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_H, '..', '..', 'bspspike'))
sys.path.insert(0, _H)
import umodel_parser as UM, decode_level as D, lightmap_decode as LM

MAPS = ['/home/neob91/Games/LutrisDX/drive_c/DX/Maps/01_NYC_UNATCOHQ.dx',
        '/home/neob91/Games/LutrisDX/drive_c/DX/Maps/01_NYC_UNATCOIsland.dx']

def brush_count(path):
    buf=open(path,'rb').read()
    h=D.parse_header(buf); names=D.parse_names(buf,h); imps=D.parse_imports(buf,h,names); exps=D.parse_exports(buf,h,names)
    return sum(1 for e in exps if D.classname(e,exps,imps,names)=='Brush')

def lumel_bytes(path):
    buf=open(path,'rb').read(); best=0
    for (i,name,size,offset) in UM.find_model_exports(path):
        try: recs,lumels = LM.walk_to_lightmap(buf, offset, size)
        except Exception: continue
        if recs: best=max(best, len(lumels))
    return best

for m in MAPS:
    name=m.split('/')[-1]; buf=open(m,'rb').read()
    big=UM.find_model_exports(m)[0]
    pm=UM.parse_model_serial(buf, big[3], big[2])
    lb=lumel_bytes(m); rays=lb*7  # ~7 rays/byte (8 bits minus row padding)
    ray_note = f"~{rays/1e6:.0f}M rays" if lb else "lumel bytes via lightmap_reconcile.py (HQ 437179, Island 4431675 → ~3M/~31M rays)"
    print(f"{name}: brushes={brush_count(m)} nodes={len(pm.nodes)} surfs={len(pm.surfs)} "
          f"verts={len(pm.verts)} lumel_bytes={lb or '(see note)'} ({ray_note})")
