+++
priority = "p2"
kind = "debug"
summary = "OceanLab N44 FAILS: world Model2's per-surf Lights run has 2 extra light refs native shouldn't emit, plus a downstream LightBits byte diff."
+++

# OceanLab N44 world Model2 Lights array has 2 extra entries

## DONE 2026-09-06 — root-caused and fixed faithfully, no mask

The gather pass's third filter — `WorldLightRadius >= |PlaneDot(light)|`, the PERPENDICULAR distance
from the light to the surf's infinite plane (`Editor 0x100a4e87`-`0x100a4ef7`, decoded 2026-09-05) —
was applied in `light.rs::bake_surf` only to the empty-run/dark decision (`visible_to_any_light`),
not to the raytrace loop that actually builds the run. The editor's gather builds each surf's light
LIST and the raytrace only prunes lights out of it, so the filter gates both.

The gap only bites in a narrow band because the raytrace samples at `plane + Normal * 4` (the
self-shadow bias), not on the plane: a light between `WorldLightRadius` and
`WorldLightRadius + bias` of the plane fails the gather but still lights lumels.
`Brush1419`'s surf 228 (plane `y = -96`) is exactly that case — `Light111`/`Light121` sit
1026.305/1027.683 from the plane against `(40+1)*25 = 1025`.

Evidence it is the editor's rule, not a tie-break:

- Across **188 cached editor reference packages** (all five ladder levels) **no** (surf, light) pair
  in any `Model.Lights` run violates the predicate, while the ratio `|PlaneDot| / WorldLightRadius`
  reaches 0.96 — the bound is tight and never crossed.
- Native's own pre-fix N=44 build violated it on exactly the two divergent pairs and nowhere else.

Fix: `uedcli-native/src/light.rs` hoists the predicate into one `gathered(li, l)` closure used by
both `visible_to_any_light` and the per-light bake loop. Pinned by
`light.rs::a_light_past_the_planes_world_radius_never_enters_the_run` (a `radius = 3` room fixture
where the light sits 101 uu from the wall plane but 97 from the nearest biased lumel) and
`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/test_gather_plane_test.py` (the
188-package invariant).

## The original divergence

`body_token_diff.py native_N44.dx ref_N44.dx model2`:

    token COUNT differs: native=11953 ued=11951
    token[11509] literal span: first differing byte at +6676 of 128650/128518
          nat=00001818f5a68541f5a68541ffffffffc48b0100002048c3b9c787c400000000
          ued=00001818f5a68541f5a68541ffffffff408b0100002048c3b9c787c400000000
    token[11946] O: nat=('light light111',) ued=('light light106',)
    token[11947] O: nat=('light light121',) ued=('None',)
    token[11948] O: nat=('light light106',) ued=('None',)
    token[11950] O: nat=('None',) ued=(b'\x00\x00\x00\x00\x00\x00\x00\x00',)

Localized to one surf: `Model.LightMap` records 214/215 shifted by +2 `iLightActors` and +132
`DataOffset`, every earlier record identical. Surf 228 (24x22 lumels, so 3*22 = 66 bytes per shadow
plane) carried three lights against the editor's one — 2 extra runs entries and 2*66 = 132 extra
`LightBits` bytes, which is the whole `LightBits` diff. Not a second bug.
