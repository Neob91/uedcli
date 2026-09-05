+++
priority = "p2"
kind = "bug"
summary = "OceanLab N3 world Model2.Polys gates NO on ItemName: native writes 'outside' for all 174 soup polys; UED22 writes 'none' for 168 (keeps 'outside' for 6). 168 name-token diffs. Pre-existing, separate from the bsp_add_vector fix."
+++

# OceanLab N3 `Model2.Polys` ItemName `outside` vs `none`

Found while landing the `bsp_add_vector` 4e-4 threshold fix
(`oceanlab-n3-world-model-divergence-bsp-add`). After that fix the soup poly tu/tv are byte-exact,
but `Model2.Polys` still gates NO on the poly `ItemName`.

## Symptom

`parity_gate.py` `BODY polys polys@model model2` differs. All 168 real token diffs are `Item`
name tokens (`_polys_tail` `ref_at(pos,"N")`):

- native `Model2.Polys` (174 polys): ItemName = `outside` for ALL 174.
- ued `Model2.Polys`: ItemName = `none` for 168, `outside` for 6.

No `b`/`PB` token diffs remain (base, normal, tu, tv all byte-exact), so this is purely the
per-poly `ItemName` field.

## Cause (hypothesis)

Native stamps every world soup FPoly's `ItemName` as `outside` (looks like a CSG outside-leaf /
group label leaking into the poly Item), where UED22 leaves most at `none` and keeps `outside` only
for the handful of polys that genuinely carry it. Pre-existing: present at the OLD 0.001 threshold
(A/B rebuild confirmed native = 174× `outside` at 0.001), so independent of the vector-dedup fix.

## Scope

Separate bug from the orphan-vert overcount (`oceanlab-n3-model2-orphan-vert-overcount-shifts`) and
from the texture-axis dedup. Needs native's world-soup FPoly `ItemName` derivation checked against
UED22. Repro: cached `_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N3.dx`; decode via
`parity_gate.canon_body` on the `Model2` `field_0x54` Polys export (native exp4, ued exp14).

## Resolved 2026-09-05

`_world_soup_fpolys` (`uedcli/native/unbuilt.py`) hardcoded `item = "OUTSIDE"` as the default and
only overrode it from the source poly. Fixed: default to `None` (serialized as the `None` FName),
propagate `src.item` only when authored. Decode of ued's world soup confirmed `OUTSIDE` is never a
CSG-fabricated default -- its 6 `OUTSIDE` polys all trace to a cube brush's AUTHORED `Item=OUTSIDE`
faces, the other 168 are `None`. So the change is faithful, not a heuristic.

- OceanLab N=3: the `polys@model model2` residual is CLEARED (only the orphan-vert `model model2`
  residual remains, `oceanlab-n3-model2-orphan-vert-overcount-shifts`).
- No regression: WanChai N=16 still PASS (its `OUTSIDE`/`Rise`/`Step` come from authored items, not
  the default); UNATCO N6/N16, NYC_Bar N16, Island N8, OceanLab N1..8 all unchanged/PASS.
- Pinned: `test_native_roundtrip.py::test_world_soup_item_defaults_to_none_not_outside`.
