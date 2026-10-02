"""Static analysis: parse a .dx's level Model, dump the e4 Lights array + light_map
i_light_actors, resolve each Lights ref, and validate.

The crash is `AddLight`: mov al,[ebx+0x1e0] with ebx = Model.Lights[iLightActors] a bad
AActor*.  So we check: (1) every FLightMapIndex.i_light_actors is a valid index into
Model.lights; (2) every Model.lights ref resolves to a real *Light* actor export (not None,
not out-of-range, not a non-light class)."""
import sys
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness")
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
from utexture_decode import load_package
from uedcli.native.umodel import parse_model_body


def resolve_ref(p, ref):
    if ref == 0:
        return ("null", None, "None")
    if ref > 0:
        if ref - 1 >= len(p.exports):
            return ("BAD-EXP-OOR", None, f"exp#{ref-1}/{len(p.exports)}")
        e = p.exports[ref - 1]
        return ("exp", p.class_of_export(ref - 1), p.names[e["nm"]])
    j = -ref - 1
    if j >= len(p.imports):
        return ("BAD-IMP-OOR", None, f"imp#{j}/{len(p.imports)}")
    imp = p.imports[j]
    return ("imp", p.names[imp[1]], p.names[imp[3]])


def analyze(path):
    print(f"\n===== {path.split('/')[-1]} =====")
    p = load_package(path)
    print(f"v{p.version}: names={len(p.names)} imports={len(p.imports)} exports={len(p.exports)}")
    # list Model/Light exports with class
    print("-- Model/Light exports --")
    for i, e in enumerate(p.exports):
        c = p.class_of_export(i) or ""
        if "Model" in c or "Light" in c:
            print(f"  [{i}] {c:<22} {p.names[e['nm']]}")
    # find the level Model export (class Model, name Model_Level or the biggest Model body)
    models = [i for i, e in enumerate(p.exports) if p.class_of_export(i) == "Model"]
    if not models:
        print("!! no Model export"); return
    # pick the one with largest ssize (the level model, not the tiny brush shapes)
    lm = max(models, key=lambda i: p.exports[i]["ssize"])
    e = p.exports[lm]
    print(f"-- level Model export [{lm}] {p.names[e['nm']]} soff={e['soff']} ssize={e['ssize']}")
    m = parse_model_body(p.buf, e["soff"], e["ssize"])
    print(f"   surfs={len(m.surfs)} nodes={len(m.nodes)} light_map={len(m.light_map)} "
          f"light_bits={len(m.light_bits)} lights={len(m.lights)}")
    # e4 Lights array — resolve each
    print("-- Model.lights (e4) --")
    for i, r in enumerate(m.lights[:40]):
        k, cls, nm = resolve_ref(p, r)
        flag = "" if (k == "exp" or k == "null") else "  <<< SUSPECT"
        if k == "exp" and cls and "Light" not in (cls or "") and cls not in ("Brush",):
            flag = f"  <<< non-light class {cls}"
        print(f"   [{i}] ref={r:<5} -> {k} {cls} {nm}{flag}")
    # light_map i_light_actors — validate range
    print("-- light_map[].i_light_actors (index into lights) --")
    bad = 0
    seen = {}
    for i, lmi in enumerate(m.light_map):
        ila = lmi.i_light_actors
        ok = (ila == -1) or (0 <= ila < len(m.lights))
        if not ok:
            bad += 1
        seen[ila] = seen.get(ila, 0) + 1
    print(f"   {len(m.light_map)} indices; distinct i_light_actors: "
          + ", ".join(f"{k}:x{v}" for k, v in sorted(seen.items())))
    print(f"   out-of-range i_light_actors: {bad}")
    # surfs with iLightMap set
    lit_surfs = [s for s in m.surfs if s.i_light_map >= 0]
    print(f"-- surfs with iLightMap>=0: {len(lit_surfs)}/{len(m.surfs)}")
    shown = 0
    for i, s in enumerate(m.surfs):
        if s.i_light_map >= 0:
            lmi = m.light_map[s.i_light_map] if s.i_light_map < len(m.light_map) else None
            ila = lmi.i_light_actors if lmi else "?"
            print(f"   surf ilm={s.i_light_map} -> i_light_actors={ila}")
            shown += 1
            if shown >= 12:
                print("   ..."); break


for path in sys.argv[1:]:
    analyze(path)
