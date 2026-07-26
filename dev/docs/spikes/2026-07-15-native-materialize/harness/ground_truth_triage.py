#!/usr/bin/env python3
"""Attribute each ground-truth section byte-divergence to a CAUSE, for triage.

`ground_truth_bytediff.py` says which sections differ on raw bytes; this tool decodes
the elements and classifies WHY, so each divergence can be triaged "and similar"
(non-deterministic editor-session artifact, excludable) vs REAL must-fix build gap.

For each section it answers the load-bearing triage question:
  * Vectors  — same SET reordered, or different values? (order determinism)
  * Points   — is native's set a SUBSET of editor's (missing geometry), superset, or disjoint?
  * Nodes    — which node fields diverge, node_flags histogram, and are the differing flag
               bits render-only (0x08 NF_PolyOccluded etc.) or build-time?
  * Surfs    — do diffs reduce to object-ref renumbering (texture/iActor) + pool-index
               reordering, or is there genuine surf-geometry divergence?
  * Zones    — is the whole diff the [1]<->[2] order swap + actor-ref renumber?
  * the bake/collision arrays (LightMap/LightBits/Bounds/LeafHulls/Lights) — counts + presence.

Loads the two .dx directly (no in-process rebuild, no normalization beyond what each
question explicitly needs — and every normalization is labelled).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli.native import umodel as UM  # noqa: E402
import utexture_decode as UT  # noqa: E402

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/gtruth/NativeCastle.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def load(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"]), pkg


def vround(v, nd=2):
    return tuple(round(c, nd) for c in v)


def SEC(t):
    print("\n" + "=" * 88 + f"\n{t}\n" + "=" * 88)


def main():
    nat, npkg = load(NATIVE)
    ed, epkg = load(EDITOR)

    # ---- Vectors ----
    SEC("VECTORS — same set reordered, or different values? (2-dp round)")
    kn = Counter(vround(v) for v in nat.vectors)
    ke = Counter(vround(v) for v in ed.vectors)
    shared = sum((kn & ke).values())
    print(f"  native={len(nat.vectors)} editor={len(ed.vectors)}  shared(multiset,2dp)={shared}")
    print(f"  only-native={sum((kn-ke).values())}  only-editor={sum((ke-kn).values())}")
    posmatch = sum(1 for a, b in zip(nat.vectors, ed.vectors) if vround(a) == vround(b))
    print(f"  positional matches (same index, 2dp): {posmatch}/{min(len(nat.vectors),len(ed.vectors))}")
    if sum((ke-kn).values()):
        print("  editor vectors not in native:", list((ke-kn).elements())[:10])
    if sum((kn-ke).values()):
        print("  native vectors not in editor:", list((kn-ke).elements())[:10])

    # ---- Points ----
    SEC("POINTS — subset / superset / disjoint? (2-dp round)")
    kn = Counter(vround(v) for v in nat.points)
    ke = Counter(vround(v) for v in ed.points)
    shared = sum((kn & ke).values())
    only_n = sum((kn - ke).values()); only_e = sum((ke - kn).values())
    print(f"  native={len(nat.points)} editor={len(ed.points)}  shared(multiset,2dp)={shared}")
    print(f"  only-native={only_n}  only-editor={only_e}")
    setn = set(kn); sete = set(ke)
    print(f"  distinct native={len(setn)} distinct editor={len(sete)} "
          f"native⊆editor? {setn <= sete}  editor⊆native? {sete <= setn}")
    print(f"  distinct only-native={len(setn-sete)}  distinct only-editor={len(sete-setn)}")
    if sete - setn:
        print("  sample editor-only points:", list(sete - setn)[:8])

    # ---- Nodes ----
    SEC("NODES — per-field divergence & node_flags")
    print("  node_flags native:", dict(sorted(Counter(n.node_flags for n in nat.nodes).items())))
    print("  node_flags editor:", dict(sorted(Counter(n.node_flags for n in ed.nodes).items())))
    print("  flag bits set (editor):", {hex(b): sum(1 for n in ed.nodes if n.node_flags & b)
                                         for b in (0x01, 0x02, 0x04, 0x08, 0x10)})
    print("  flag bits set (native):", {hex(b): sum(1 for n in nat.nodes if n.node_flags & b)
                                         for b in (0x01, 0x02, 0x04, 0x08, 0x10)})
    # editor node_flags with 0x08 masked off -> does the rest match native's build-time flags?
    def mask_occ(nf):
        return nf & ~0x08
    ce = Counter(mask_occ(n.node_flags) for n in ed.nodes)
    print("  editor node_flags with 0x08 (NF_PolyOccluded) masked OFF:", dict(sorted(ce.items())))
    # ordered field divergence (exact, no tolerance) over common length
    fields = ["i_vert_pool", "num_vertices", "i_surf", "i_front", "i_back", "i_plane",
              "i_zone", "node_flags", "i_collision_bound", "i_render_bound", "i_leaf"]
    hist = Counter()
    plane_mismatch = 0
    for a, b in zip(nat.nodes, ed.nodes):
        if vround(a.plane, 3) != vround(b.plane, 3):
            plane_mismatch += 1
        for f in fields:
            if getattr(a, f) != getattr(b, f):
                hist[f] += 1
    print(f"  ordered exact per-field mismatch counts over {min(len(nat.nodes),len(ed.nodes))} nodes:")
    print(f"    plane(3dp) mismatches: {plane_mismatch}")
    for f, c in hist.most_common():
        print(f"    {f:<20} {c}")
    # iZone remapped: native zone k <-> editor zone map. Test hypothesis native(0,1)==editor(0,2)
    zmap = {1: 2, 2: 1, 0: 0, 3: 3}
    zmatch = sum(1 for a, b in zip(nat.nodes, ed.nodes)
                 if tuple(zmap.get(z, z) for z in a.i_zone) == tuple(b.i_zone))
    print(f"  node iZone match under native->editor zone remap {{1:2,2:1}}: "
          f"{zmatch}/{min(len(nat.nodes),len(ed.nodes))}")

    # ---- Surfs ----
    SEC("SURFS — reduce to ref-renumber + pool reorder, or real geometry diff?")
    fields = ["poly_flags", "p_base", "v_normal", "v_texture_u", "v_texture_v",
              "i_brush_poly", "i_zone", "i_light_map"]
    hist = Counter()
    for a, b in zip(nat.surfs, ed.surfs):
        for f in fields:
            if getattr(a, f) != getattr(b, f):
                hist[f] += 1
    # object-ref fields resolved to names
    tex_n = Counter(npkg.name_of_ref(s.texture_ref) if s.texture_ref else None for s in nat.surfs)
    tex_e = Counter(epkg.name_of_ref(s.texture_ref) if s.texture_ref else None for s in ed.surfs)
    print(f"  ordered exact per-field mismatch over {min(len(nat.surfs),len(ed.surfs))} surfs:")
    for f, c in hist.most_common():
        print(f"    {f:<16} {c}")
    print(f"  texture multiset equal (by resolved name)? {tex_n == tex_e}")
    print(f"    distinct textures native={len(tex_n)} editor={len(tex_e)}")
    pf_n = Counter(s.poly_flags for s in nat.surfs)
    pf_e = Counter(s.poly_flags for s in ed.surfs)
    print(f"  poly_flags multiset equal? {pf_n == pf_e}")
    if pf_n != pf_e:
        print("    native poly_flags:", dict(sorted(pf_n.items())))
        print("    editor poly_flags:", dict(sorted(pf_e.items())))

    # ---- Zones ----
    SEC("ZONES — is the whole diff the [1]<->[2] order swap + actor-ref renumber?")
    for lbl, m, pkg in (("native", nat, npkg), ("editor", ed, epkg)):
        print(f"  {lbl}:")
        for zi, z in enumerate(m.zones):
            an = pkg.name_of_ref(z.actor_ref) if z.actor_ref else None
            print(f"    zone[{zi}] actor={an!r:<22} conn={z.connectivity:#x} vis={z.visibility:#x}")

    # ---- bake / collision arrays ----
    SEC("BAKE / COLLISION ARRAY PRESENCE")
    print(f"  LightMap(a8):  native={len(nat.light_map)}   editor={len(ed.light_map)}")
    print(f"  LightBits(b4): native={len(nat.light_bits)}  editor={len(ed.light_bits)}")
    print(f"  Bounds(c0):    native={len(nat.bounds)}      editor={len(ed.bounds)}")
    print(f"  LeafHulls(cc): native={len(nat.leaf_hulls)}  editor={len(ed.leaf_hulls)}")
    print(f"  Lights(e4):    native={len(nat.lights)}      editor={len(ed.lights)}")
    print(f"  NumSharedSides native={nat.num_shared_sides} editor={ed.num_shared_sides}")
    print(f"  Verts:         native={len(nat.verts)}       editor={len(ed.verts)}")
    # per-node NumVertices distribution (verts pool driver)
    nvn = Counter(n.num_vertices for n in nat.nodes)
    nve = Counter(n.num_vertices for n in ed.nodes)
    print(f"  sum NumVertices over nodes: native={sum(n.num_vertices for n in nat.nodes)} "
          f"editor={sum(n.num_vertices for n in ed.nodes)}")
    print(f"  NumVertices hist native={dict(sorted(nvn.items()))}")
    print(f"  NumVertices hist editor={dict(sorted(nve.items()))}")


if __name__ == "__main__":
    main()
